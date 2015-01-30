from openerp.osv import osv, fields
from openerp import SUPERUSER_ID, tools
from openerp.osv.orm import browse_record
from openerp.tools.translate import _

class res_groups(osv.osv):
    _name = 'res.groups'
    _inherit = 'res.groups'
    
    _columns = {
                'app_functions': fields.many2many('ida.app.functions','group_app_function_rel','group_id','func_id','Granted Functions')
                }

        
    

        