from openerp.osv import osv, fields, expression
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp

class product_product(osv.osv):
    _name = 'product.product'
    _inherit = 'product.product'
    
    _columns = {
                'ean_enabled': fields.property(
                                               '',
                                               type='boolean', view_load=True, string='Enable EAN'),
                }