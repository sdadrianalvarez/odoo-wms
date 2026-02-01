# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class BoxMovementWizard(models.TransientModel):
    """
    Wizard para realizar operaciones sobre cajas
    """
    _name = "box.movement.wizard"
    _description = "Box Movement Wizard"

    box_id = fields.Many2one("product.box", string="Box")
    rack_id = fields.Many2one("stock.location", string="Rack", domain=[('is_rack', '=', True)])
    x_coordinate = fields.Integer(string="X Coordinate")
    y_coordinate = fields.Integer(string="Y Coordinate")
    z_coordinate = fields.Integer(string="Z Coordinate")

    def action_picking(self):
        """Ejecutar operación de picking"""
        if not self.box_id:
            raise UserError(_('Please select a box first.'))
        return self.box_id.action_move()

    def action_put_in(self):
        """Ejecutar operación de put-in"""
        if not self.box_id:
            raise UserError(_('Please select a box first.'))
        return self.box_id.action_put_in_target()

    def action_clean_up(self):
        """
        Ejecutar operación de clean-up
        Reorganiza todas las cajas desde dummy a sus ubicaciones
        """
        # Buscar cajas en cualquier ubicación dummy
        out_location_boxes = self.env["product.box"].search([
            ("state", "=", "outlocation"),
            ("parent_location.is_dummy", "=", True)
        ], order="pos_y desc", limit=20)
        
        if not out_location_boxes:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Clean-up Needed'),
                    'message': _('No boxes found in dummy location.'),
                    'type': 'info',
                }
            }
        
        # Usar el método de clean_up de la primera caja encontrada
        return out_location_boxes[0].action_clean_up()

    def action_box_naming(self):
        """
        Asignar automáticamente cajas a ubicaciones vacías
        """
        empty_boxes = self.env["product.box"].search([("parent_location", "=", False)])
        assigned_count = 0
        
        for box in empty_boxes:
            location = self.env["stock.location"].search([
                ("is_box", "=", True),
                ("box_id", "=", False)
            ], limit=1)
            
            if location:
                box.write({
                    "parent_location": location.id,
                    "pos_x": location.pos_x,
                    "pos_y": location.pos_y,
                    "pos_z": location.pos_z,
                })
                location.write({"box_id": box.id})
                assigned_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Boxes Assigned'),
                'message': _('%d boxes were assigned to available locations.') % assigned_count,
                'type': 'success',
            }
        }

    def action_search_box(self):
        """
        Buscar caja por coordenadas
        CORREGIDO: Ahora busca correctamente usando parent_location
        """
        if not self.rack_id:
            raise UserError(_('Please select a rack first.'))
        
        # MÉTODO 1: Buscar por coordenadas y parent_location
        # Primero buscamos la ubicación específica que coincide con las coordenadas
        specific_location = self.env["stock.location"].search([
            ("is_box", "=", True),
            ("pos_x", "=", self.x_coordinate),
            ("pos_y", "=", self.y_coordinate),
            ("pos_z", "=", self.z_coordinate),
            ("location_id", "child_of", self.rack_id.id)
        ], limit=1)
        
        if not specific_location:
            raise UserError(_(
                'No location found at coordinates:\nX=%d, Y=%d, Z=%d\nin rack %s'
            ) % (self.x_coordinate, self.y_coordinate, self.z_coordinate, self.rack_id.name))
        
        # Ahora buscamos la caja en esa ubicación
        box = self.env["product.box"].search([
            "|",
            ("rack_location", "=", specific_location.id),
            ("parent_location", "=", specific_location.id)
        ], limit=1)
        
        # MÉTODO 2 (alternativo): Buscar directamente por coordenadas
        # Este método es más simple y directo
        if not box:
            box = self.env["product.box"].search([
                ("pos_x", "=", self.x_coordinate),
                ("pos_y", "=", self.y_coordinate),
                ("pos_z", "=", self.z_coordinate),
                "|",
                ("parent_location.location_id", "=", self.rack_id.id),
                ("rack_location.location_id", "=", self.rack_id.id)
            ], limit=1)
        
        if not box:
            raise UserError(_(
                'No box found at coordinates:\nX=%d, Y=%d, Z=%d\nin rack %s'
            ) % (self.x_coordinate, self.y_coordinate, self.z_coordinate, self.rack_id.name))
        
        # Construir mensaje informativo
        if box.parent_location.is_box:
            message_text = _("Box Found!\n\nID: %s\nLocation: %s\nCoordinates: X=%d, Y=%d, Z=%d\nState: %s") % (
                box.location_identification,
                box.parent_location.name,
                box.pos_x,
                box.pos_y,
                box.pos_z,
                dict(box._fields['state'].selection).get(box.state)
            )
        else:
            message_text = _(
                "Box Found!\n\nID: %s\nCurrently at: %s\nAssigned to: %s\nCoordinates: X=%d, Y=%d, Z=%d\nState: %s"
            ) % (
                box.location_identification,
                box.parent_location.name,
                box.rack_location.name if box.rack_location else "N/A",
                box.pos_x,
                box.pos_y,
                box.pos_z,
                dict(box._fields['state'].selection).get(box.state)
            )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Box Found'),
                'message': message_text,
                'type': 'success',
                'sticky': True,
            }
        }

    def action_search_location(self):
        """
        Buscar ubicación de una caja
        """
        if not self.box_id:
            raise UserError(_('Please select a box first.'))
        
        box = self.box_id
        
        if box.parent_location.is_dummy:
            message_text = _(
                "Box: %s\n\nAssigned Coordinates:\nX: %d, Y: %d, Z: %d\n\nCurrently located at dummy location"
            ) % (box.location_identification, box.pos_x, box.pos_y, box.pos_z)
        else:
            message_text = _(
                "Box: %s\n\nCoordinates:\nX: %d, Y: %d, Z: %d\n\nLocation: %s\nRack: %s"
            ) % (
                box.location_identification,
                box.pos_x,
                box.pos_y,
                box.pos_z,
                box.parent_location.name,
                box.parent_location.location_id.name if box.parent_location.location_id else "N/A"
            )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Box Location'),
                'message': message_text,
                'type': 'info',
                'sticky': True,
            }
        }

    def action_outside_warehouse(self):
        """
        Mostrar cajas que están fuera del almacén
        """
        boxes = self.env["product.box"].search([
            ("parent_location.usage", "!=", "internal")
        ])
        
        if not boxes:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('All Boxes Inside'),
                    'message': _('All boxes are currently inside the warehouse.'),
                    'type': 'success',
                }
            }
        
        box_list = "\n".join([
            "- %s (X:%d, Y:%d, Z:%d)" % (box.location_identification, box.pos_x, box.pos_y, box.pos_z) 
            for box in boxes
        ])
        message_text = _("These boxes are out of warehouse:\n\n%s") % box_list
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Boxes Outside Warehouse'),
                'message': message_text,
                'type': 'warning',
                'sticky': True,
            }
        }
