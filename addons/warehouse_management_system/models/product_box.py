# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import datetime
import logging

_logger = logging.getLogger(__name__)

class ProductBox(models.Model):
    """
    Modelo principal de Cajas (Unidades de Almacenamiento)
    Adaptado para Odoo SaaS - comunicación vía Middleware
    """
    _name = 'product.box'
    _description = 'Product Box (Storage Unit)'
    _rec_name = "location_identification"
    _order = 'location_identification'

    location_identification = fields.Char(
        string="Location Identifier",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'New',
        help="Identificador único de la caja (ej: QBE1004004002)"
    )

    key = fields.Many2one('product.box.key', string='Key Type')

    # Ubicación actual
    parent_location = fields.Many2one(
        "stock.location",
        string="Current Location",
        help="Ubicación actual de la caja"
    )

    # Ubicación asignada (donde debe estar normalmente)
    rack_location = fields.Many2one(
        "stock.location",
        string="Assigned Rack Location",
        help="Ubicación asignada en el rack (donde pertenece la caja)"
    )

    # Coordenadas 3D de la ubicación asignada
    pos_x = fields.Integer(string="X Position", help="Posición horizontal")
    pos_y = fields.Integer(string="Y Position", help="Posición de profundidad")
    pos_z = fields.Integer(string="Z Position", help="Posición de altura")

    # Historial de movimientos
    box_move_ids = fields.One2many(
        "product.box.line",
        "box_id",
        string="Movement History"
    )

    # Estado de la caja
    state = fields.Selection([
        ("inlocation", "In Assigned Location"),
        ("outlocation", "Out of Location")
    ], string="State", default="inlocation")

    # ========== VALIDACIONES ==========
    
    @api.constrains('parent_location')
    def _check_parent_location_required(self):
        """Validar que toda caja tenga una ubicación actual"""
        for box in self:
            if not box.parent_location:
                raise ValidationError(_(
                    'Current Location es obligatorio para todas las cajas.\n'
                    'Por favor asigne una ubicación (ej: Puerta) antes de guardar.'
                ))

    @api.constrains('parent_location')
    def _check_unique_box_per_location(self):
        """Validar que no haya 2 cajas en la misma posición del rack"""
        for box in self:
            if box.parent_location and box.parent_location.is_box and box.parent_location.is_rack:
                # Buscar otras cajas en la misma ubicación
                existing = self.search([
                    ('id', '!=', box.id),
                    ('parent_location', '=', box.parent_location.id),
                    ('state', '=', 'inlocation')
                ])
                if existing:
                    raise ValidationError(_(
                        'La ubicación %s ya está ocupada por la caja %s.\n'
                        'No puede haber dos cajas en la misma posición del rack.'
                    ) % (box.parent_location.name, existing[0].location_identification))
    
    # ========== FIN VALIDACIONES ==========

    @api.model_create_multi
    def create(self, vals_list):
        """
        Generar identificador automático al crear caja
        Actualizado para Odoo 19 - ahora recibe lista de valores
        AUTO-ASIGNA PUERTA si no se proporciona parent_location
        """
        for vals in vals_list:
            # Generar ID de caja
            if vals.get('location_identification', 'New') == 'New':
                if vals.get('key'):
                    key = self.env['product.box.key'].browse(vals['key'])
                    vals['location_identification'] = (
                        key.key +
                        datetime.date.today().strftime('%Y') +
                        self.env['ir.sequence'].next_by_code('pbk.' + key.key)
                    )
                else:
                    raise UserError(_('Please select a Box Key Type before creating the box.'))
            
            # AUTO-ASIGNAR PUERTA si no tiene parent_location
            if not vals.get('parent_location'):
                puerta = self.env['stock.location'].search([
                    ('name', '=', 'Puerta'),
                    ('is_box', '=', True)
                ], limit=1)
                
                if puerta:
                    vals['parent_location'] = puerta.id
                    _logger.info(f"Auto-asignada ubicación 'Puerta' a caja {vals.get('location_identification')}")
                else:
                    raise UserError(_(
                        'No se encontró la ubicación "Puerta".\n'
                        'Por favor cree la ubicación Puerta o asigne manualmente una ubicación a la caja.'
                    ))

        records = super(ProductBox, self).create(vals_list)
        return records

    def _calculate_blocking_boxes(self):
        """
        Calcular qué cajas están bloqueando el acceso a esta caja
        (todas las cajas con Y menor en la misma columna X,Z)

        Returns:
            list: Lista de cajas que deben moverse
        """
        self.ensure_one()

        blocking_boxes = self.search([
            ('pos_y', '<', self.pos_y),
            ('pos_x', '=', self.pos_x),
            ('pos_z', '=', self.pos_z),
            ('parent_location.location_id', '=', self.parent_location.location_id.id),
            ('state', '=', 'inlocation')
        ], order="pos_y asc")

        return blocking_boxes

    def _prepare_operation_data(self, operation_type, target_location=None):
        """
        Preparar datos para enviar al middleware

        Args:
            operation_type: 'picking', 'put_in', 'clean_up'
            target_location: ubicación destino (opcional)
        """
        self.ensure_one()

        # Generar ID único de operación
        operation_id = f"{operation_type.upper()}-{self.id}-{fields.Datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # Datos base de la operación
        operation_data = {
            "operation_id": operation_id,
            "operation_type": operation_type,
            "timestamp": fields.Datetime.now().isoformat(),
            "priority": "normal",
            "target_box": {
                "id": self.location_identification,
                "odoo_id": self.id,
                "current_pos": {
                    "x": self.pos_x,
                    "y": self.pos_y,
                    "z": self.pos_z
                }
            }
        }

        # Para picking: calcular secuencia de movimientos
        if operation_type == 'picking':
            operation_data['target_box']['target_pos'] = {"x": 0, "y": 0, "z": 0}
            operation_data['sequence'] = self._build_picking_sequence()

        # Para put_in: calcular secuencia de movimientos
        elif operation_type == 'put_in':
            if not target_location:
                target_location = self.rack_location

            operation_data['target_box']['target_pos'] = {
                "x": target_location.pos_x,
                "y": target_location.pos_y,
                "z": target_location.pos_z
            }
            operation_data['sequence'] = self._build_put_in_sequence(target_location)

        return operation_data

    def _build_picking_sequence(self):
        """
        Construir secuencia de movimientos para picking
        """
        self.ensure_one()
        blocking_boxes = self._calculate_blocking_boxes()
        dummy_location = self.env['stock.location'].get_dummy_location()

        if not dummy_location:
            raise UserError(_('No dummy location configured. Please create one first.'))

        sequence = []
        step = 1

        # Primero mover las cajas bloqueantes a dummy
        for box in blocking_boxes:
            sequence.append({
                "step": step,
                "action": "move_to_dummy",
                "box_id": box.location_identification,
                "box_odoo_id": box.id,
                "from": {"x": box.pos_x, "y": box.pos_y, "z": box.pos_z},
                "to": {"x": dummy_location.pos_x or 0, "y": dummy_location.pos_y or 0, "z": dummy_location.pos_z or 0},
                "description": f"Move box {box.location_identification} to dummy rack"
            })
            step += 1

        # Luego mover la caja objetivo a posición de entrega
        sequence.append({
            "step": step,
            "action": "deliver",
            "box_id": self.location_identification,
            "box_odoo_id": self.id,
            "from": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "to": {"x": 0, "y": 0, "z": 0},
            "description": f"Deliver box {self.location_identification} to central position"
        })

        return sequence

    def _build_put_in_sequence(self, target_location):
        """
        Construir secuencia de movimientos para put-in
        """
        self.ensure_one()

        # Buscar cajas que bloquean la ubicación objetivo
        blocking_boxes = self.search([
            ('pos_y', '<', target_location.pos_y),
            ('pos_x', '=', target_location.pos_x),
            ('pos_z', '=', target_location.pos_z),
            ('parent_location.location_id', '=', target_location.location_id.id),
            ('state', '=', 'inlocation')
        ], order="pos_y asc")

        dummy_location = self.env['stock.location'].get_dummy_location()

        sequence = []
        step = 1

        # Mover cajas bloqueantes a dummy
        for box in blocking_boxes:
            sequence.append({
                "step": step,
                "action": "move_to_dummy",
                "box_id": box.location_identification,
                "box_odoo_id": box.id,
                "from": {"x": box.pos_x, "y": box.pos_y, "z": box.pos_z},
                "to": {"x": dummy_location.pos_x or 0, "y": dummy_location.pos_y or 0, "z": dummy_location.pos_z or 0},
                "description": f"Move box {box.location_identification} to dummy"
            })
            step += 1

        # Colocar la caja en su ubicación
        sequence.append({
            "step": step,
            "action": "place",
            "box_id": self.location_identification,
            "box_odoo_id": self.id,
            "from": {"x": self.parent_location.pos_x or 0, "y": self.parent_location.pos_y or 0, "z": self.parent_location.pos_z or 0},
            "to": {"x": target_location.pos_x, "y": target_location.pos_y, "z": target_location.pos_z},
            "description": f"Place box {self.location_identification} in target location"
        })

        return sequence

    def action_move(self):
        """
        Acción de PICKING - Extraer caja del almacén
        Adaptado para SaaS: envía operación al middleware en lugar de IoT Box
        """
        self.ensure_one()

        try:
            # Obtener configuración del middleware
            middleware = self.env['middleware.config'].get_active_config()

            # Preparar datos de la operación
            operation_data = self._prepare_operation_data('picking')

            # Enviar al middleware
            response = middleware.send_operation(operation_data)

            # Registrar operación enviada
            _logger.info(f"Picking operation sent: {operation_data['operation_id']}")

            # Mostrar mensaje al usuario
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Operation Sent'),
                    'message': _('Picking operation sent to middleware.\nOperation ID: %s') % operation_data['operation_id'],
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            _logger.error(f"Failed to send picking operation: {str(e)}")
            raise UserError(_(
                'Failed to send picking operation to middleware:\n%s'
            ) % str(e))

    def action_put_in_target(self):
        """
        Acción de PUT-IN - Almacenar caja en rack
        """
        self.ensure_one()

        try:
            middleware = self.env['middleware.config'].get_active_config()
            operation_data = self._prepare_operation_data('put_in')
            response = middleware.send_operation(operation_data)

            _logger.info(f"Put-in operation sent: {operation_data['operation_id']}")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Operation Sent'),
                    'message': _('Put-in operation sent to middleware.\nOperation ID: %s') % operation_data['operation_id'],
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            _logger.error(f"Failed to send put-in operation: {str(e)}")
            raise UserError(_('Failed to send put-in operation:\n%s') % str(e))

    def action_clean_up(self):
        """
        Acción de CLEAN-UP - Reorganizar cajas desde dummy a sus ubicaciones originales
        Busca cajas en CUALQUIER ubicación dummy (Dummy-01, Dummy-02, etc.)
        Usa rack_location para saber dónde devolver cada caja
        """
        self.ensure_one()

        try:
            middleware = self.env['middleware.config'].get_active_config()

            # Buscar cajas en cualquier ubicación dummy (is_dummy=True)
            boxes_in_dummy = self.search([
                ('parent_location.is_dummy', '=', True),
                ('state', '=', 'outlocation')
            ], order='pos_y desc', limit=20)

            if not boxes_in_dummy:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Clean-up Needed'),
                        'message': _('No boxes found in dummy location.'),
                        'type': 'info',
                        'sticky': False,
                    }
                }

            # Construir lista de cajas a devolver
            # current_pos = coordenadas actuales en dummy (pos_x, pos_y, pos_z)
            # target_pos  = coordenadas originales del rack (rack_location)
            boxes_to_return = []
            for box in boxes_in_dummy:
                if not box.rack_location:
                    _logger.warning(f"Caja {box.location_identification} no tiene rack_location, se omite del clean-up")
                    continue
                
                boxes_to_return.append({
                    "box_id": box.location_identification,
                    "box_odoo_id": box.id,
                    "current_pos": {
                        "x": box.pos_x,
                        "y": box.pos_y,
                        "z": box.pos_z
                    },
                    "target_pos": {
                        "x": box.rack_location.pos_x,
                        "y": box.rack_location.pos_y,
                        "z": box.rack_location.pos_z
                    }
                })

            if not boxes_to_return:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Clean-up Needed'),
                        'message': _('No boxes with valid rack locations found.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }

            # Construir secuencia de movimientos para el middleware
            sequence = []
            step = 1
            for box_data in boxes_to_return:
                sequence.append({
                    "step": step,
                    "action": "place",
                    "box_id": box_data["box_id"],
                    "box_odoo_id": box_data["box_odoo_id"],
                    "from": box_data["current_pos"],
                    "to": box_data["target_pos"],
                    "description": f"Return box {box_data['box_id']} from dummy to rack"
                })
                step += 1

            operation_data = {
                "operation_id": f"CLEANUP-{fields.Datetime.now().strftime('%Y%m%d-%H%M%S')}",
                "operation_type": "clean_up",
                "timestamp": fields.Datetime.now().isoformat(),
                "priority": "low",
                "target_box": {
                    "id": boxes_to_return[0]["box_id"],
                    "current_pos": boxes_to_return[0]["current_pos"],
                    "target_pos": boxes_to_return[0]["target_pos"]
                },
                "sequence": sequence
            }

            response = middleware.send_operation(operation_data)

            _logger.info(f"Clean-up operation sent: {operation_data['operation_id']} - {len(boxes_to_return)} cajas")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Clean-up Started'),
                    'message': _('Clean-up operation sent.\n%d boxes will be returned to their locations.') % len(boxes_to_return),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            _logger.error(f"Failed to send clean-up operation: {str(e)}")
            raise UserError(_('Failed to send clean-up operation:\n%s') % str(e))

    @api.model
    def api_picking(self, location_identification):
        """
        API endpoint para picking (llamado desde middleware u otros sistemas)

        Args:
            location_identification: ID de la caja

        Returns:
            dict: resultado de la operación
        """
        ret = {"error": "OK"}
        product_box = self.search([("location_identification", "=", location_identification)])

        if not product_box:
            ret['error'] = f'Identificador erróneo: *{location_identification}*'
            return ret

        return product_box.action_move()

    @api.model
    def api_putin(self, location_identification):
        """API endpoint para put-in"""
        ret = {"error": "OK"}
        product_box = self.search([("location_identification", "=", location_identification)])

        if not product_box:
            ret['error'] = 'Identificador erróneo'
            return ret

        return product_box.action_put_in_target()

    @api.model
    def api_clean_up(self, location_identification):
        """API endpoint para clean-up"""
        ret = {"error": "OK"}
        product_box = self.search([("location_identification", "=", location_identification)])

        if not product_box:
            ret['error'] = 'Identificador erróneo'
            return ret

        return product_box.action_clean_up()


class ProductBoxLine(models.Model):
    """
    Líneas de historial de movimientos de cajas
    """
    _name = 'product.box.line'
    _description = 'Product Box Movement Line'
    _order = 'create_date desc'

    box_id = fields.Many2one('product.box', string='Box', required=True, ondelete='cascade')
    source_location_id = fields.Many2one('stock.location', string='From Location')
    destination_location_id = fields.Many2one('stock.location', string='To Location')
    create_date = fields.Datetime(string='Movement Date', readonly=True)
