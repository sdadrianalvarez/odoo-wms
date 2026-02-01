# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

class WarehouseAPI(http.Controller):
    
    @http.route('/api/wms/operation/complete', type='http', auth='public', methods=['POST'], csrf=False)
    def operation_complete(self, **kwargs):
        """
        Endpoint para que el middleware notifique operaciones completadas
        
        Payload esperado (JSON-RPC):
        {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "operation_id": "PUT_IN-29-20260131-075555",
                "operation_type": "put_in",
                "box_id": "QBE12026000029",
                "status": "completed",
                "new_location": {
                    "x": 3,
                    "y": 1,
                    "z": 1
                }
            },
            "id": null
        }
        """
        try:
            # Leer el body del request
            body = request.httprequest.get_data(as_text=True)
            data_wrapper = json.loads(body)
            
            # Extraer params del wrapper JSON-RPC
            data = data_wrapper.get('params', {})
            
            _logger.info(f"📥 Callback recibido del middleware: {json.dumps(data, indent=2)}")
            
            operation_id = data.get('operation_id')
            operation_type = data.get('operation_type')
            box_id = data.get('box_id')
            status = data.get('status')
            new_location = data.get('new_location', {})
            
            # Validar datos requeridos
            if not all([operation_id, operation_type, box_id, status]):
                result = {
                    'success': False,
                    'error': 'Faltan campos requeridos'
                }
                return Response(
                    json.dumps({"jsonrpc": "2.0", "id": data_wrapper.get('id'), "result": result}),
                    content_type='application/json'
                )
            
            # Buscar la caja
            box = request.env['product.box'].sudo().search([
                ('location_identification', '=', box_id)
            ], limit=1)
            
            if not box:
                _logger.error(f"❌ Caja no encontrada: {box_id}")
                result = {
                    'success': False,
                    'error': f'Caja no encontrada: {box_id}'
                }
                return Response(
                    json.dumps({"jsonrpc": "2.0", "id": data_wrapper.get('id'), "result": result}),
                    content_type='application/json'
                )
            
            # Guardar ubicación original para historial
            source_location_id = box.parent_location.id if box.parent_location else False
            
            # Actualizar según el tipo de operación
            if status == 'completed':
                if operation_type in ['put_in', 'place']:
                    # === PUT IN: Mover caja al rack ===
                    x, y, z = new_location.get('x'), new_location.get('y'), new_location.get('z')
                    
                    _logger.info(f"🔍 Buscando ubicación en ({x},{y},{z})")
                    
                    # Buscar la ubicación física en el rack
                    target_location = request.env['stock.location'].sudo().search([
                        ('pos_x', '=', x),
                        ('pos_y', '=', y),
                        ('pos_z', '=', z),
                        ('is_box', '=', True),
                        ('is_rack', '=', True)
                    ], limit=1)
                    
                    if target_location:
                        box.sudo().write({
                            'parent_location': target_location.id,
                            'rack_location': target_location.id,
                            'pos_x': x,
                            'pos_y': y,
                            'pos_z': z,
                            'state': 'inlocation'
                        })
                        _logger.info(f"✅ PUT_IN: Caja {box_id} → {target_location.name} ({x},{y},{z})")
                    else:
                        _logger.warning(f"⚠️ Ubicación no encontrada para ({x},{y},{z}), actualizando solo coordenadas")
                        box.sudo().write({
                            'pos_x': x,
                            'pos_y': y,
                            'pos_z': z,
                            'state': 'inlocation'
                        })
                
                elif operation_type in ['picking', 'deliver']:
                    # === PICKING: Mover caja a Puerta y RESETEAR coordenadas a (0,0,0) ===
                    puerta = request.env['stock.location'].sudo().search([
                        ('name', '=', 'Puerta'),
                        ('is_box', '=', True)
                    ], limit=1)
                    
                    if puerta:
                        box.sudo().write({
                            'parent_location': puerta.id,
                            'pos_x': 0,
                            'pos_y': 0,
                            'pos_z': 0,
                            'state': 'outlocation'
                        })
                        _logger.info(f"✅ PICKING: Caja {box_id} → Puerta (0,0,0)")
                    else:
                        _logger.error("❌ Ubicación 'Puerta' no encontrada")
                
                elif operation_type == 'move_to_dummy':
                    # === MOVE TO DUMMY: Mover caja bloqueante a área temporal ===
                    x, y, z = new_location.get('x'), new_location.get('y'), new_location.get('z')
                    
                    # Buscar posición libre en dummy con esas coordenadas
                    dummy_location = request.env['stock.location'].sudo().search([
                        ('pos_x', '=', x),
                        ('pos_y', '=', y),
                        ('pos_z', '=', z),
                        ('is_dummy', '=', True),
                        ('is_box', '=', True)
                    ], limit=1)
                    
                    if dummy_location:
                        box.sudo().write({
                            'parent_location': dummy_location.id,
                            'pos_x': x,
                            'pos_y': y,
                            'pos_z': z,
                            'state': 'outlocation'
                        })
                        _logger.info(f"✅ DUMMY: Caja {box_id} → {dummy_location.name} ({x},{y},{z})")
                    else:
                        # Si no encuentra la posición exacta, usar primera dummy libre
                        dummy_any = request.env['stock.location'].sudo().search([
                            ('is_dummy', '=', True),
                            ('is_box', '=', True)
                        ], limit=1)
                        
                        if dummy_any:
                            box.sudo().write({
                                'parent_location': dummy_any.id,
                                'pos_x': dummy_any.pos_x,
                                'pos_y': dummy_any.pos_y,
                                'pos_z': dummy_any.pos_z,
                                'state': 'outlocation'
                            })
                            _logger.info(f"✅ DUMMY (fallback): Caja {box_id} → {dummy_any.name} ({dummy_any.pos_x},{dummy_any.pos_y},{dummy_any.pos_z})")
                        else:
                            _logger.error("❌ No se encontró ubicación Dummy disponible")
                
                # Registrar movimiento en historial
                try:
                    request.env['product.box.line'].sudo().create({
                        'box_id': box.id,
                        'source_location_id': source_location_id,
                        'destination_location_id': box.parent_location.id if box.parent_location else False,
                    })
                    _logger.info(f"📝 Historial registrado para caja {box_id}")
                except Exception as hist_error:
                    _logger.warning(f"⚠️ No se pudo registrar historial: {hist_error}")
                
                # Re-leer la caja para obtener datos actualizados
                box = request.env['product.box'].sudo().search([
                    ('location_identification', '=', box_id)
                ], limit=1)
                
                result = {
                    'success': True,
                    'message': f'Caja {box_id} actualizada correctamente',
                    'box_state': {
                        'current_location': box.parent_location.name if box.parent_location else 'N/A',
                        'coordinates': f"({box.pos_x},{box.pos_y},{box.pos_z})",
                        'state': box.state
                    }
                }
                
                return Response(
                    json.dumps({"jsonrpc": "2.0", "id": data_wrapper.get('id'), "result": result}),
                    content_type='application/json'
                )
            
            else:
                _logger.error(f"❌ Operación falló: {operation_id}")
                result = {
                    'success': False,
                    'error': f'Operación en estado: {status}'
                }
                return Response(
                    json.dumps({"jsonrpc": "2.0", "id": data_wrapper.get('id'), "result": result}),
                    content_type='application/json'
                )
        
        except Exception as e:
            _logger.error(f"❌ Error en callback: {str(e)}", exc_info=True)
            result = {
                'success': False,
                'error': str(e)
            }
            return Response(
                json.dumps({"jsonrpc": "2.0", "id": None, "result": result}),
                content_type='application/json',
                status=500
            )
    
    @http.route('/api/wms/health', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def health_check(self):
        """Health check endpoint"""
        result = {
            'status': 'ok',
            'service': 'Odoo WMS API'
        }
        return Response(
            json.dumps(result),
            content_type='application/json'
        )
