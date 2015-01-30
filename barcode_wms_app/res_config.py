from openerp.osv import osv, fields
from openerp import SUPERUSER_ID, tools
from openerp.tools.translate import _

class stock_config_settings(osv.osv_memory):
    _name = 'stock.config.settings'
    _inherit = 'stock.config.settings'
    
    _columns = {
                'app_scan_material': fields.boolean(_('Scan EAN'),
                                                    help=_('Scan EAN or Internal Reference on APP')),
                }
    
    def get_default_ean(self, cr, uid, fields, context=None):
        product_obj = self.pool.get('product.product')
        product_ids = product_obj.search(cr, uid, [], context=context)
        if product_ids:
            if isinstance(product_ids, (int, long)):
                product_ids = [product_ids]
            ean_enabled = product_obj.browse(cr, uid, product_ids, context=context)[0].ean_enabled
        else:
            ean_enabled = False
        return {'app_scan_material': ean_enabled}

    def set_default_ean(self, cr, uid, ids, context=None):
        config = self.browse(cr, uid, ids[0], context=context)
        property_obj = self.pool.get('ir.property')
        domain = [('name', '=', 'property_enable_ean')]
        property_ids = property_obj.search(cr, uid, domain, context=context)
        if property_ids:
            if len(property_ids):
                property_ids = property_ids[0]
            property_obj.write(cr, uid, property_ids, {'value_integer': config.app_scan_material}, context=context)
