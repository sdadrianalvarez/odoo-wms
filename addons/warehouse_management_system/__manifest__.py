# -*- coding: utf-8 -*-
{
    'name': 'Warehouse Management System - Library',
    'version': '19.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Sistema de gestión de almacén automatizado para biblioteca con integración PLC',
    'description': """
        Sistema de Gestión de Almacén para Biblioteca
        ==============================================
        
        Características principales:
        * Gestión de cajas (unidades de almacenamiento) con coordenadas 3D
        * Racks con múltiples niveles de profundidad
        * Zona dummy para almacenamiento temporal
        * Operaciones: Picking, Put-in, Clean-up
        * Integración con PLC Beckhoff vía Middleware
        * Compatible con Odoo SaaS (sin dependencias externas)
        
        Versión: 19.0 (Odoo SaaS)
        Autor: Adrian Alvarez
        Fecha: Enero 2026
    """,
    'author': 'Adrian Alvarez',
    'website': 'https://github.com/sdadrianalvarez',
    'depends': ['stock', 'base'],
    'data': [
        'security/ir.model.access.csv',
        'data/middleware_config_data.xml',
        'views/product_box_views.xml',
        'views/stock_location_views.xml',
        'views/box_movement_wizard_views.xml',
        'views/middleware_config_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
