from openerp.osv import osv, fields
from openerp import SUPERUSER_ID, tools
from openerp.osv.orm import browse_record
from openerp.tools.translate import _
import urllib
import urllib2
import xml.etree.ElementTree as ET


class ida_app_taobao_auth(osv.osv):
    _name = 'ida.app.taobao.auth'
    
    _columns = {
                'taobao_user_nick': fields.char(u'Taobao User Name', size=50, required=True),
                'access_token': fields.char(u'Access Token', size=200, required=True),
                'refresh_token': fields.char(u'Refresh Token', size=200, required=True),
                'is_active': fields.boolean(u'Is Active'),
                }
    def get_auth(self, cr, uid, context=None):
        if not context:
            context = {}
        res = []
        auth_ids = self.search(cr, SUPERUSER_ID, [], context=context)
        if auth_ids:
            if isinstance(auth_ids, (int, long)):
                auth_ids = [auth_ids]
            auths = self.read(cr, SUPERUSER_ID, auth_ids, ['taobao_user_nick', 'is_active'], context=context)
            for auth in auths:
                res.append(auth)
        return res
    
    def set_auth(self, cr, uid, auth_id, context=None):
        if not context:
            context = {}
        vals_reset = {'is_active': False}
        domain_reset = [('is_active', '=', True)]
        vals = {'is_active': True}
        auth_ids = self.search(cr, SUPERUSER_ID, domain_reset, context=context)
        if auth_ids:
            self.write(cr, SUPERUSER_ID, auth_ids, vals_reset, context=context)
            self.write(cr, SUPERUSER_ID, auth_id, vals, context=context)
            return {'Code': 1, 'Msg': 'Success'}
        else:
            return {'Code': 0, 'Msg': 'No Active Taobao ID'}
        
    def retrieve_orders(self, cr, uid, context=None):
        self.get_orders(cr, uid, [], context)
    def get_orders(self, cr, uid, ids, context=None):
        if not context:
            context = {}
        domain_auth = [('is_active', '=', True)]
        auth_ids = self.search(cr, SUPERUSER_ID, domain_auth, context=context)
        if auth_ids:
            if isinstance(auth_ids, (int, long)):
                auth_ids = [auth_ids]
            auth = self.browse(cr, SUPERUSER_ID, auth_ids, context=context)[0]
            refresh_token = auth.refresh_token
            access_token = auth.access_token
            taobao_user_nick = auth.taobao_user_nick
            partner_obj = self.pool.get('res.partner')
            product_obj = self.pool.get('product.product')
            domain_partner = [('name', '=', 'Taobao')]
            partner_ids = partner_obj.search(cr, SUPERUSER_ID, domain_partner, context=context)
            if partner_ids:
                if isinstance(partner_ids, (int, long)):
                    partner_ids = [partner_ids]
            else:
                return
            url = 'https://gw.api.tbsandbox.com/router/rest'
            values = {
                      'method': 'taobao.trades.sold.get',
                      'access_token': access_token,
                      'v': '2.0',
                      'fields': 'orders',
                      }
            data = urllib.urlencode(values)
            req = urllib2.Request(url, data)
            res = urllib2.urlopen(req)
            
            order_obj = self.pool.get('sale.order')
            order_line_obj = self.pool.get('sale.order.line')
            pl_obj = self.pool.get('product.pricelist')
            pl_ids = pl_obj.search(cr, SUPERUSER_ID, [('type', '=', 'sale')], context=context)
            if pl_ids:
                if isinstance(pl_ids, (int, long)):
                    pl_ids = [pl_ids]
            else:
                return
            root = ET.fromstring(res.read())
            for trades in root:
                for trade in trades:
                    for order_items in trade:
                        for order_item in order_items:
                            order = {}
                            order.update(pricelist_id=pl_ids[0])
                            order.update(partner_id=partner_ids[0])
                            order.update(partner_invoice_id=partner_ids[0])
                            order.update(partner_shipping_id=partner_ids[0])
                            order_line = {}
                            order_line.update(name='')
                            
                            for field in order_item:
                                tag = field.tag
                                val = field.text
                                if tag == 'oid':
                                    order.update(name=val)
                                if tag == 'title':
                                    domain_product = [('name', '=', val)]
                                    product_ids = product_obj.search(cr, SUPERUSER_ID, domain_product, context=context)
                                    if product_ids:
                                        if isinstance(product_ids, (int, long)):
                                            product_ids = [product_ids]
                                        product = product_obj.browse(cr, SUPERUSER_ID, product_ids, context=context)[0]
                                        order_line.update(product_id=product.id)
                                        order_line.update(price_unit=product.list_price)
                                        order_line.update(purchase_price=product.list_price)
                                        order_line.update(product_uom=product.uom_id.id)
                                        order_line.update(product_uos=product.uom_id.id)
                                if tag == 'num':
                                    order_line.update(product_uom_qty=val)
                                    order_line.update(product_uos_qty=val)
                                if tag == 'discount_fee':
                                    order_line.update(discount=val)
                            if order_line.has_key('product_id'):
                                order_ids = order_obj.search(cr, SUPERUSER_ID, [('name', '=', order['name'])], context=context)
                                if order_ids:
                                    continue
                                order_line.update(discount=float(order_line['discount']) * 100 / (float(order_line["product_uom_qty"]) * float(order_line["price_unit"])))
                                order_id = order_obj.create(cr, SUPERUSER_ID, order, context=context)
                                order_line.update(order_id=order_id)
                                order_line_id = order_line_obj.create(cr, SUPERUSER_ID, order_line, context=context)
#                                 order_obj.write(cr, SUPERUSER_ID, order_id, {'order_line': [order_line_id]}, context=context)
                                order_obj.action_button_confirm(cr, SUPERUSER_ID, [order_id], context=context)
                                
                                    
                            
                
            
            