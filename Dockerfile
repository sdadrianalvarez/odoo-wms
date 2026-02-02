FROM odoo:19.0

# Copiar addons personalizados
COPY addons /mnt/extra-addons

# Ajustar permisos
USER root
RUN chown -R odoo:odoo /mnt/extra-addons
USER odoo

# Exponer puerto
EXPOSE 8069

# Arrancar Odoo incluyendo addons personalizados
CMD ["odoo", "--addons-path=/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons"]


