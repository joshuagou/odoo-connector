from openerp.osv import osv, fields
from openerp import SUPERUSER_ID, tools
from openerp.osv.orm import browse_record
from openerp.tools.translate import _

class ida_app_license(osv.osv):
    _name = 'ida.app.license'
    
    _columns = {
               'product_code': fields.char(u'Product ID', size=100, required=True),
               'mac_id': fields.char(u'Assigned Device ID', size=100),
               'is_active': fields.boolean(u'Activated'),
               }
    _defaults = {
                 'is_active': False,
                 }
    