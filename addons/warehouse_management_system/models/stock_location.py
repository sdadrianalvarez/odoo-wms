# -*- coding: utf-8 -*-

from odoo import models, fields, api

class StockLocation(models.Model):
    """
    Extensión de stock.location para soportar el sistema de warehouse
    """
    _inherit = 'stock.location'

    # Tipos de ubicación
    is_box = fields.Boolean(
        string="Is Box Location",
        help="Marca si esta ubicación almacena una caja específica"
    )
    is_rack = fields.Boolean(
        string="Is Rack",
        help="Marca si esta ubicación es un rack principal"
    )
    is_dummy = fields.Boolean(
        string="Is Dummy/Temporary Storage",
        help="Marca si esta ubicación es para almacenamiento temporal"
    )
    
    # Relación con caja
    box_id = fields.Many2one(
        'product.box',
        string="Box",
        help="Caja asignada a esta ubicación"
    )
    
    # Coordenadas 3D
    pos_x = fields.Integer(
        string="X Position (Width)",
        help="Posición horizontal en el rack"
    )
    pos_y = fields.Integer(
        string="Y Position (Depth)",
        help="Posición de profundidad (frente a fondo)"
    )
    pos_z = fields.Integer(
        string="Z Position (Height)",
        help="Posición de altura en el rack"
    )
    
    # Configuración para ubicaciones dummy
    max_box_dummy = fields.Integer(
        string="Dummy Max Capacity",
        help="Capacidad máxima de cajas en zona dummy"
    )
    limit = fields.Integer(
        string="Threshold Limit",
        help="Límite de cajas antes de ejecutar clean-up automático"
    )
    
    # Configuración para racks
    max_box = fields.Integer(
        string="Max Number of Boxes",
        help="Número máximo de cajas que puede contener"
    )
    
    @api.model
    def get_box_location(self, pos_x, pos_y, pos_z, rack_location_id):
        """
        Obtener la ubicación de una caja por sus coordenadas
        """
        return self.search([
            ('pos_x', '=', pos_x),
            ('pos_y', '=', pos_y),
            ('pos_z', '=', pos_z),
            ('location_id', '=', rack_location_id),
            ('is_box', '=', True)
        ], limit=1)
    
    @api.model
    def get_dummy_location(self):
        """
        Obtener la ubicación dummy activa
        """
        return self.search([
            ('is_dummy', '=', True),
            ('usage', '=', 'internal')
        ], limit=1)
    
    @api.model
    def get_next_available_location(self):
        """
        Obtener la siguiente ubicación disponible (sin caja asignada)
        """
        return self.search([
            ('is_box', '=', True),
            ('box_id', '=', False)
        ], limit=1)
