# -*- coding: utf-8 -*-

from odoo import models, fields

class DisplayFinalDialogBox(models.TransientModel):
    """
    Modelo transitorio para mostrar mensajes al usuario
    """
    _name = "display.final.dialog.box"
    _description = "Display Dialog Box"

    text = fields.Text(string="Message", readonly=True)
