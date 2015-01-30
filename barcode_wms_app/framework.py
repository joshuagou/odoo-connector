from openerp.osv import osv, fields
import xmlrpclib
import logging
from openerp.tools.translate import _
from collections import OrderedDict
from datetime import date, datetime
import urllib
import md5

#
class ida_app_framework(osv.osv):
    _name = 'ida.app.framework'
    _auto = False
    _description = 'iLoda APP Framework'
    
    def ui_access(self, cr, uid, context=None):
        user_obj = self.pool.get('res.users')
        user = user_obj.browse(cr, uid, uid)
        result = {}
        ordered_result = {}
        if user.groups_id:
            for x in user.groups_id:
                for y in x.app_functions:
                    result[y.function_code] = y.name
        return result
              
    
class ida_app_functions(osv.osv):
    _name = 'ida.app.functions'
    _inherit = ['mail.thread']
    _description = 'iLoda APP Functions'
    
    _columns = {
                'function_code': fields.char('Function Code', Size=20),
                'name': fields.char('Function Name', Size=20),
                'description': fields.char('Description', Size=64),
                'groups': fields.many2many('res.groups', 'group_app_function_rel', 'func_id', 'group_id', 'Groups')
                }
    
    
    

    
