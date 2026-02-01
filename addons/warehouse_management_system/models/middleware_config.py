# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class MiddlewareConfig(models.Model):
    """
    Configuración de conexión con el Middleware
    Este modelo almacena la URL del middleware y maneja toda la comunicación
    """
    _name = 'middleware.config'
    _description = 'Middleware Configuration'
    _rec_name = 'name'

    name = fields.Char(string='Configuration Name', required=True, default='Default Middleware')
    middleware_url = fields.Char(
        string='Middleware URL',
        required=True,
        help='URL del middleware (ej: https://abc123.ngrok.io o http://localhost:8000)'
    )
    api_key = fields.Char(
        string='API Key',
        help='Clave de autenticación para el middleware (opcional)'
    )
    active = fields.Boolean(string='Active', default=True)
    timeout = fields.Integer(string='Timeout (seconds)', default=30)
    retry_count = fields.Integer(string='Retry Count', default=3)
    last_connection_test = fields.Datetime(string='Last Connection Test')
    connection_status = fields.Selection([
        ('not_tested', 'Not Tested'),
        ('success', 'Connected'),
        ('failed', 'Connection Failed')
    ], string='Connection Status', default='not_tested', readonly=True)
    
    @api.constrains('middleware_url')
    def _check_middleware_url(self):
        """Validar formato de URL"""
        for record in self:
            if record.middleware_url:
                if not (record.middleware_url.startswith('http://') or 
                        record.middleware_url.startswith('https://')):
                    raise UserError(_('Middleware URL must start with http:// or https://'))
    
    def test_connection(self):
        """
        Probar conexión con el middleware
        """
        self.ensure_one()
        try:
            # Preparar datos de prueba
            test_data = {
                'operation_id': 'TEST-CONNECTION',
                'operation_type': 'test',
                'timestamp': fields.Datetime.now().isoformat()
            }
            
            # Intentar enviar
            response = self._send_to_middleware('/api/v1/test', test_data)
            
            self.write({
                'last_connection_test': fields.Datetime.now(),
                'connection_status': 'success'
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Successfully connected to middleware at %s') % self.middleware_url,
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            self.write({
                'last_connection_test': fields.Datetime.now(),
                'connection_status': 'failed'
            })
            _logger.error(f"Middleware connection test failed: {str(e)}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Failed'),
                    'message': _('Could not connect to middleware: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def _send_to_middleware(self, endpoint, data):
        """
        Enviar datos al middleware usando Odoo's HTTP client
        
        Args:
            endpoint: endpoint del API (ej: '/api/v1/operations')
            data: diccionario con los datos a enviar
            
        Returns:
            dict: respuesta del middleware
        """
        self.ensure_one()
        
        # Construir URL completa
        url = self.middleware_url.rstrip('/') + endpoint
        
        # Preparar headers
        headers = {
            'Content-Type': 'application/json',
        }
        
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        # Odoo SaaS permite hacer requests externos usando su cliente HTTP interno
        # Usamos el método estándar de Odoo para hacer requests
        try:
            # En Odoo SaaS, usamos las herramientas internas de HTTP
            import requests  # Odoo SaaS tiene requests disponible internamente
            
            response = requests.post(
                url,
                json=data,
                headers=headers,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            
            _logger.info(f"Successfully sent operation to middleware: {data.get('operation_id')}")
            
            return response.json()
            
        except Exception as e:
            _logger.error(f"Failed to send to middleware: {str(e)}")
            raise UserError(_(
                'Failed to communicate with middleware:\n'
                'URL: %s\n'
                'Error: %s'
            ) % (url, str(e)))
    
    @api.model
    def get_active_config(self):
        """Obtener la configuración activa del middleware"""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            raise UserError(_(
                'No active middleware configuration found.\n'
                'Please configure middleware connection in:\n'
                'Inventory → Configuration → Middleware Configuration'
            ))
        return config
    
    def send_operation(self, operation_data):
        """
        Enviar operación al middleware
        
        Args:
            operation_data: diccionario con los datos de la operación
        """
        self.ensure_one()
        return self._send_to_middleware('/api/v1/operations', operation_data)
