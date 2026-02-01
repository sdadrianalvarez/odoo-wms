# -*- coding: utf-8 -*-

from odoo import models, fields, api

class ProductBoxKey(models.Model):
    """
    Clase base para secuencias de nomenclatura de las cajas
    Cada key genera una secuencia automática
    """
    _name = 'product.box.key'
    _description = 'Product Box Key/Sequence'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    key = fields.Char(string='Key Code', required=True, size=10)
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Al crear una key, automáticamente crear su secuencia en Odoo
        Actualizado para Odoo 19 - ahora recibe lista de valores
        """
        # Crear las secuencias asociadas ANTES de crear los registros
        for vals in vals_list:
            self.env['ir.sequence'].create({
                'name': vals['name'],
                'code': 'pbk.' + vals['key'],
                'active': True,
                'padding': 6,
                'number_next': 1,
                'number_increment': 1
            })
        
        # Crear los registros
        records = super(ProductBoxKey, self).create(vals_list)
        return records
