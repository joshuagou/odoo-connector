# import werkzeug
# from werkzeug.wrappers import Response
from openerp import SUPERUSER_ID
from openerp.addons.web import http
from openerp.osv import fields, osv
import urllib
import urllib2
import logging
import datetime
import xml.etree.ElementTree as ET
from datetime import datetime as dt, date
import xmlrpclib
from flask import json, Response
from openerp.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT
import time
from openerp.tools.translate import _
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)
 
class ida_app_framework(osv.osv):
    _name = 'ida.app.framework'
    _inherit = 'ida.app.framework'
    
    def _in_out_submit(self, cr, uid, picking=None, partial_data=None, direction='in', context=None):    
        if not picking or not partial_data or not isinstance(picking, str) or not isinstance(partial_data, dict):
            return {'Code': 0, 'Msg': 'Picking or some other info is missing!'}
        for key, value in partial_data.iteritems():
            if not isinstance(value, (int, long)) or value <= 0:
                return {'Code': 0, 'Msg': 'Incorrect Qty!'}
        if not context:
            context = {}
        if direction == 'in':
            picking_obj = self.pool.get('stock.picking.in')
            domain_pk = [('type', '=', 'in'), ('state', '=', 'assigned'), ('name', '=', picking)]
        else:
            picking_obj = self.pool.get('stock.picking.out')
            domain_pk = [('type', '=', 'out'), ('state', '=', 'assigned'), ('name', '=', picking)]
        
        picking_ids = picking_obj.search(cr, uid, domain_pk, context=context)
        if picking_ids:
            partial_data_delivery = {
                                     'delivery_date': time.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                                     }
            if isinstance(picking_ids, (int, long)):
                picking_ids = [picking_ids]
            picking = picking_obj.browse(cr, uid, picking_ids, context=context)[0]
            for move in picking.move_lines:
                move_detail = {}
                move_detail['Material'] = move.product_id.name
                move_detail['OpenQty'] = move.product_qty
                move_detail['GRQty'] = 0
                move_detail.update(product_uom=move.product_uom.id, prodlot_id=move.prodlot_id.id)
                if move.product_id.cost_method == 'average':
                    product_currency_id = move.product_id.company_id.currency_id and move.product_id.company_id.currency_id.id
                    picking_currency_id = move.picking_id.company_id.currency_id and move.picking_id.company_id.currency_id.id
                    move_detail.update(product_price=move.product_id.standard_price,
                                       product_currency=product_currency_id or picking_currency_id or False)
                if partial_data.has_key(move.product_id.name) and partial_data[move.product_id.name] > 0:
                    if move.product_qty >= partial_data[move.product_id.name]:
                        move_detail.update(GRQty=partial_data[move.product_id.name])
                        partial_data[move.product_id.name] = 0
                    else:
                        move_detail.update(GRQty=move.product_qty)
                        partial_data[move.product_id.name] -= move.product_qty
                partial_data_delivery['move%s' % (move.id)] = {
                                                               'product_id': move.product_id.id,
                                                               'product_qty': move_detail['GRQty'],
                                                               'product_uom': move.product_uom.id,
                                                               'prodlot_id': move.prodlot_id.id,
                                                               }
                if move_detail.has_key('product_price') and move_detail.has_key('product_currency'):
                    partial_data_delivery['move%s' % (move.id)].update(product_price=move_detail['product_price'],
                                                                       product_currency=move_detail['product_currency'])
            for key, value in partial_data.iteritems():
                if value > 0:
                    return {'Code': 0, 'Msg': 'Open Qty is not enough!'}
            done = picking_obj.do_partial(cr, uid, picking_ids, partial_data_delivery, context=context)
            if direction == 'in':
                return {'Code': 1, 'Msg': 'Received Successfully'}
            else:
                return {'Code': 1, 'Msg': 'Delivered Successfully'}
        else:
            return {'Code': 0, 'Msg': 'Picking does not exist'}
    def get_picking_in(self, cr, uid, po=None, context=None):
        if not context:
            context = {}
        ean_enabled = self._ean_enabled(cr, uid, context)
        picking_obj = self.pool.get('stock.picking.in')
        domain_pk = [('type', '=', 'in'), ('state', '=', 'assigned'), '|', ('name', '=', po), ('purchase_id.name', '=', po)]
        picking_ids = picking_obj.search(cr, uid, domain_pk, context=context)
        res = []
        if picking_ids:
            if isinstance(picking_ids, (int, long)):
                picking_ids = [picking_ids]
            pickings = picking_obj.browse(cr, uid, picking_ids, context=context)
            for picking in pickings:
                bill = {}
                bill['Name'] = picking.name
                bill['PO'] = picking.purchase_id.name
                bill['Moves'] = []
                for move in picking.move_lines:
                    if move.state == 'assigned':
                        move_item = next((x for x in bill['Moves'] if x['Material'] == move.product_id.name), None)
                        if move_item:
                            move_item['Qty'] += move.product_qty
                        else:
                            item = {}
                            item['Material'] = move.product_id.name
                            if ean_enabled:
                                item['Code'] = move.product_id.ean13 if move.product_id.ean13 else ''
                            else:
                                item['Code'] = move.product_id.code if move.product_id.code else ''
                            item['Qty'] = move.product_qty
                            bill['Moves'].append(item)
                res.append(bill)
        return {'res': res}
    
    def goods_receiving(self, cr, uid, picking=None, partial_data=None, context=None):
        return self._in_out_submit(cr, uid, picking, partial_data, direction='in', context=context)
    
    def get_picking_out(self, cr, uid, so=None, context=None):
        if not context:
            context = {}
        ean_enabled = self._ean_enabled(cr, uid, context)
        picking_obj = self.pool.get('stock.picking.out')
        domain_pk = [('type', '=', 'out'), ('state', '=', 'assigned'), '|', ('name', '=', so), ('sale_id.name', '=', so)]
        picking_ids = picking_obj.search(cr, uid, domain_pk, context=context)
        res = []
        if picking_ids:
            if isinstance(picking_ids, (int, long)):
                picking_ids = [picking_ids]
            pickings = picking_obj.browse(cr, uid, picking_ids, context=context)
            for picking in pickings:
                bill = {}
                bill['Name'] = picking.name
                bill['PO'] = picking.sale_id.name
                bill['Moves'] = []
                for move in picking.move_lines:
                    if move.state == 'assigned':
                        move_item = next((x for x in bill['Moves'] if x['Material'] == move.product_id.name), None)
                        if move_item:
                            move_item['Qty'] += move.product_qty
                        else:
                            item = {}
                            item['Material'] = move.product_id.name
                            if ean_enabled:
                                item['Code'] = move.product_id.ean13 if move.product_id.ean13 else ''
                            else:
                                item['Code'] = move.product_id.code if move.product_id.code else ''
                            item['Qty'] = move.product_qty
                            bill['Moves'].append(item)
                res.append(bill)
        return {'res': res}
    
    def goods_issue(self, cr, uid, picking=None, partial_data=None, context=None):
        return self._in_out_submit(cr, uid, picking, partial_data, direction='out', context=context)
    
    def new_cycle_count(self, cr, uid, context=None):
        if not context:
            context = {}
        return self.pool.get('ir.sequence').get(cr, uid, 'stock.inventory.ref') or _('Unknown Inventory Ref')
    def cycle_count(self, cr, uid, stock=None, context=None):
        if not stock or not isinstance(stock, dict):
            return {'Code': 0, 'Msg': 'Failed due to incorrect info!'}
        if not context:
            context = {}
        ref = stock['Ref']
        location = stock['Location']
        vals = {
                'name': stock['Ref'],
                }
        vals_lines = {}
        vals_new = []
        inv_obj = self.pool.get('stock.inventory')
        inv_line_obj = self.pool.get('stock.inventory.line')
        domain_inv = [('name', '=', ref)]
        inv_ids = inv_obj.search(cr, uid, domain_inv, context=context)
        location_obj = self.pool.get('stock.location')
        move_obj = self.pool.get('stock.move')
        uom_obj = self.pool.get('product.uom')
        fill_obj = self.pool.get('stock.fill.inventory')
        domain_loc = [('name', '=', location)]
        location_ids = location_obj.search(cr, uid, domain_loc, context=context)
        if location_ids:
            if len(location_ids):
                location_ids = location_ids[0]
            if not inv_ids:
                inv_ids = inv_obj.create(cr, uid, vals, context=context)
                fill_obj.create(cr, uid, {'location_id': location_ids, 'recursive': False, 'set_stock_zero': True})
                res = {}
                datas = {}
                res[location] = {}
                move_ids = move_obj.search(cr, uid, ['|',('location_dest_id','=',location_ids),('location_id','=',location_ids),('state','=','done')], context=context)
                local_context = dict(context)
                local_context['raise-exception'] = False
                for move in move_obj.browse(cr, uid, move_ids, context=context):
                    lot_id = move.prodlot_id.id
                    prod_id = move.product_id.id
                    if move.location_dest_id.id != move.location_id.id:
                        if move.location_dest_id.id == location_ids:
                            qty = uom_obj._compute_qty_obj(cr, uid, move.product_uom,move.product_qty, move.product_id.uom_id, context=local_context)
                        else:
                            qty = -uom_obj._compute_qty_obj(cr, uid, move.product_uom,move.product_qty, move.product_id.uom_id, context=local_context)


                        if datas.get((prod_id, lot_id)):
                            qty += datas[(prod_id, lot_id)]['product_qty']

                        datas[(prod_id, lot_id)] = {'product_id': prod_id, 'location_id': location_ids, 'product_qty': qty, 'product_uom': move.product_id.uom_id.id, 'prod_lot_id': lot_id}

                if datas:
                    res[location_ids] = datas
                for stock_move in res.values():
                    for stock_move_details in stock_move.values():
                        stock_move_details.update({'inventory_id': inv_ids})
                        domain = []
                        for field, value in stock_move_details.items():
                            if field == 'product_qty':
                                domain.append((field, 'in', [value,'0']))
                                continue
                            domain.append((field, '=', value))
                        stock_move_details.update({'product_qty': 0})

                        line_ids = inv_line_obj.search(cr, uid, domain, context=context)

                        if not line_ids:
                            inv_line_obj.create(cr, uid, stock_move_details, context=context)
            if isinstance(inv_ids, (int, long)):
                inv_ids = [inv_ids]
            invs = inv_obj.browse(cr, uid, inv_ids, context=context)
            if invs[0].state not in ('draft', 'confirm'):
                return {'Code': 0, 'Msg': 'The inventory ref is not in Draft or Confirm status!'}
            product_obj = self.pool.get('product.product')
            for key, value in stock['Inv'].iteritems():
                flag = False
                for inv_line in invs[0].inventory_line_id:
                    if key == inv_line.product_id.name and location == inv_line.location_id.name:
                        vals_lines[inv_line.id] = {'product_qty': value}
                        flag = True
                if not flag:
                    product_ids = product_obj.search(cr, uid, [('name', '=', key)], context=context)
                    if product_ids:
                        if isinstance(product_ids, (int, long)):
                            product_ids = [product_ids]
                        product_id = product_ids[0]
                        product = product_obj.browse(cr, uid, product_ids, context=context)[0]
                        product_uom = product.uom_id.id
                        product_qty = value
                        location_id = location_ids
                        vals_new.append({
                                         'inventory_id': inv_ids[0],
                                         'product_id': product_id,
                                         'product_uom': product_uom,
                                         'product_qty': product_qty,
                                         'location_id': location_id,
                                         })
            for key, value in vals_lines.iteritems():
                inv_line_obj.write(cr, uid, key, value, context=context)
            for item in vals_new:
                inv_line_obj.create(cr, uid, item, context=context)   
            return {'Code': 1, 'Msg': 'Submitted successfully!'}
        else:
            return {'Code': 0, 'Msg': 'The location doesn\'t exist!'}
    
    def stock_move(self, cr, uid, data=None, context=None): 
        if not data or not isinstance(data, dict):
            return {'Code': 0, 'Msg': 'Failed due to incorrect info!'}
        if not context:
            context = {}
        source_loc = data['Source']
        target_loc = data['Target']
        if source_loc == target_loc:
            return {'Code': 0, 'Msg': 'Cannot move inside a single location!'}
        moves = data['Moves']
        if not source_loc:
            source_loc = 'Input'
        if not self.assert_location(cr, uid, source_loc, context) or not self.assert_location(cr, uid, target_loc, context):
            return {'Code': 0, 'Msg': 'Location must be either internal or inventory!'}
        stock = self._query_stock(cr, uid, source_loc, None, context)
        if not stock.get(source_loc):
            return {'Code': 0, 'Msg': 'Stock in source location %s is not enough!' % (source_loc, )}
        for key, value in moves.iteritems():
            if stock[source_loc].get(key):
                if stock[source_loc][key] < value:
                    return {'Code': 0, 'Msg': '%s stock in source location %s is not enough!' % (key, source_loc)}
            else:
                return {'Code': 0, 'Msg': '%s stock in source location %s is not enough!' % (key, source_loc)}
        location_obj = self.pool.get('stock.location')
        picking_obj = self.pool.get('stock.picking')
        move_obj = self.pool.get('stock.move')
        source_loc_id = location_obj.search(cr, uid, [('name', '=', source_loc)], context=context)
        if not source_loc_id:
            return {'Code': 0, 'Msg': 'Source location %s doesn\'t exist' % (source_loc, )}
        if isinstance(source_loc_id, list):
            source_loc_id = source_loc_id[0]
        target_loc_id = location_obj.search(cr, uid, [('name', '=', target_loc)], context=context)
        if not target_loc_id:
            return {'Code': 0, 'Msg': 'Target location %s doesn\'t exist' % (target_loc, )}
        if isinstance(target_loc_id, list):
            target_loc_id = target_loc_id[0]
        domain_loc = [('usage', '=', 'inventory'), ('scrap_location', '=', True), ('active', '=', True)]
        scrap_ids = location_obj.search(cr, uid, domain_loc, context=context)
        source_scrap = False
        target_scrap = False
        if scrap_ids:
            if isinstance(scrap_ids, (int, long)):
                scrap_ids = [scrap_ids]
            scraps = location_obj.browse(cr, uid, scrap_ids, context=context)
            for scrap in scraps:
                if scrap.name == source_loc:
                    source_scrap = True
                if scrap.name == target_loc:
                    target_scrap = True
        picking_id = picking_obj.create(cr, uid, {}, context=context)
        product_obj = self.pool.get('product.product')
        data = {}
        for key, value in moves.iteritems():
            product_ids = product_obj.search(cr, uid, [('name', '=', key)], context=context)
            if product_ids:
                if isinstance(product_ids, (int, long)):
                    product_ids = [product_ids]
                product = product_obj.browse(cr, uid, product_ids, context=context)[0]
                vals = {
                        'name': '[%s] %s' % (product.name, product.code if product.code else ''),
                        'product_id': product_ids[0],
                        'product_qty': value,
                        'product_uom': product.uom_id.id,
                        'product_uos_qty': value,
                        'product_uos': product.uom_id.id,
                        'location_id': source_loc_id,
                        'location_dest_id': target_loc_id,
                        'picking_id': picking_id,
                        'scrapped': True if not source_scrap and target_scrap else False,             
                        }
                move_id = move_obj.create(cr, uid, vals, context=context)
                move_obj.action_confirm(cr, uid, [move_id], context=context)
                data['move%s' % (move_id, )] = {
                                                'product_id': product_ids[0],
                                                'product_qty': value,
                                                'product_uom': product.uom_id.id
                                                }
        picking_obj.do_partial(cr, uid, [picking_id], data, context=context)
        picking_obj.action_done(cr, uid, [picking_id], context=context)
        return {'Code': 1, 'Msg': 'Succeed!'}
            
    def sync_product(self, cr, uid, context=None):
        product_obj = self.pool.get('product.product')
        product_ids = product_obj.search(cr, uid, [], context=context)
        res = {}
        ean_enabled = self._ean_enabled(cr, uid, context)
        if product_ids:
            if isinstance(product_ids, (int, long)):
                product_ids = [product_ids]
            products = product_obj.browse(cr, uid, product_ids, context=context)
            for product in products:
                if ean_enabled:
                    if product.ean13 and product.name:
                        res[product.ean13] = product.name
                else:
                    if product.code and product.name:
                        res[product.code] = product.name
        return res
    
    def assert_location(self, cr, uid, location=None, context=None):
        if not context:
            context = {}
        location_obj = self.pool.get('stock.location')
        domain = [('name', '=', location), ('active', '=', True), ('usage', 'in', ('internal', 'inventory'))]
        location_ids = location_obj.search(cr, uid, domain, context=context)
        if location_ids:
            return True
        else:
            return False
        
    def _query_stock(self, cr, uid, location=None, material=None, context=None):
        if not context:
            context = {}
        res = {}
        if location and material:
            domain = [('state','=','done'), '|', ('location_dest_id.name','=',location), ('location_id.name','=',location),
                      ('product_id.name', '=', material)]
        elif not location and not material:
            domain = [('state','=','done')]
        elif not location and material:
            domain = [('state','=','done'), ('product_id.name', '=', material)]
        else:
            domain = [('state','=','done'), '|', ('location_dest_id.name','=',location), ('location_id.name','=',location)]
        move_obj = self.pool.get('stock.move')
        uom_obj = self.pool.get('product.uom')
        move_ids = move_obj.search(cr, uid, domain, context=context)
        if move_ids:
            if isinstance(move_ids, (int, long)):
                move_ids = [move_ids]
            moves = move_obj.browse(cr, uid, move_ids, context=context)
            location_ids = {}
            if location:
                location_obj = self.pool.get('stock.location')
                domain_loc = [('name', '=', location)]
                location_id = location_obj.search(cr, uid, domain_loc, context=context)
                if location_id:
                    if len(location_id):
                        location_id = location_id[0]
                    location_ids[location_id] = location
            else:
                for move in moves:
                    if not location_ids.get(move.location_id.id):
                        location_ids[move.location_id.id] = move.location_id.name
                    if not location_ids.get(move.location_dest_id.id):
                        location_ids[move.location_dest_id.id] = move.location_dest_id.name
            for key, value in location_ids.iteritems():
                location = value
                res[location] = {}
                for move in moves:
                    material = move.product_id.name
                    if move.location_dest_id.id != move.location_id.id:
                        if move.location_dest_id.id == key:
                            qty = uom_obj._compute_qty_obj(cr, uid, move.product_uom,move.product_qty, move.product_id.uom_id, context=context)
                        elif move.location_id.id == key:
                            qty = -uom_obj._compute_qty_obj(cr, uid, move.product_uom,move.product_qty, move.product_id.uom_id, context=context)
                        else:
                            continue
                        if res[location].get(material):
                            res[location][material] += qty
                        else:
                            res[location][material] = qty
            
        return res
    
    def query_stock(self, cr, uid, location=None, material=None, context=None):
        if not context:
            context = {}
        res = {}
        ean_enabled = self._ean_enabled(cr, uid, context)
        if location and material:
            if ean_enabled:
                domain = [('state','=','done'), '|', ('location_dest_id.name','=',location), ('location_id.name','=',location),
                         '|', ('product_id.ean13', '=', material), ('product_id.name', '=', material)]
            else:
                domain = [('state','=','done'), '|', ('location_dest_id.name','=',location), ('location_id.name','=',location),
                         '|', ('product_id.default_code', '=', material), ('product_id.name', '=', material)]
        elif not location and not material:
            domain = [('state','=','done')]
        elif not location and material:
            if ean_enabled:
                domain = [('state','=','done'), '|', ('product_id.ean13', '=', material), ('product_id.name', '=', material)]
            else:
                domain = [('state','=','done'), '|', ('product_id.default_code', '=', material), ('product_id.name', '=', material)]
        else:
            domain = [('state','=','done'), '|', ('location_dest_id.name','=',location), ('location_id.name','=',location)]
        move_obj = self.pool.get('stock.move')
        uom_obj = self.pool.get('product.uom')
        move_ids = move_obj.search(cr, uid, domain, context=context)
        if move_ids:
            if isinstance(move_ids, (int, long)):
                move_ids = [move_ids]
            moves = move_obj.browse(cr, uid, move_ids, context=context)
            location_ids = {}
            if location:
                location_obj = self.pool.get('stock.location')
                domain_loc = [('name', '=', location)]
                location_id = location_obj.search(cr, uid, domain_loc, context=context)
                if location_id:
                    if len(location_id):
                        location_id = location_id[0]
                    location_ids[location_id] = location
            else:
                for move in moves:
                    if not location_ids.get(move.location_id.id):
                        location_ids[move.location_id.id] = move.location_id.name
                    if not location_ids.get(move.location_dest_id.id):
                        location_ids[move.location_dest_id.id] = move.location_dest_id.name
            for key, value in location_ids.iteritems():
                location = value
                res[location] = {}
                for move in moves:
                    code = move.product_id.ean13 if ean_enabled else move.product_id.code
                    code = code if code else ''
                    material = '[%s] %s' % (code, move.product_id.name)
                    if move.location_dest_id.id != move.location_id.id:
                        if move.location_dest_id.id == key:
                            qty = uom_obj._compute_qty_obj(cr, uid, move.product_uom,move.product_qty, move.product_id.uom_id, context=context)
                        elif move.location_id.id == key:
                            qty = -uom_obj._compute_qty_obj(cr, uid, move.product_uom,move.product_qty, move.product_id.uom_id, context=context)
                        else:
                            continue
                        if res[location].get(material):
                            res[location][material] += qty
                        else:
                            res[location][material] = qty
            
        return res
    
    def _ean_enabled(self, cr, uid, context=None):
        property_obj = self.pool.get('ir.property')
        domain = [('name', '=', 'property_enable_ean')]
        property_ids = property_obj.search(cr, uid, domain, context=context)
        if property_ids:
            if len(property_ids):
                property_ids = property_ids[0]
            pty = property_obj.browse(cr, uid, property_ids, context=context).value_integer
            return pty
        return False
    
    def get_auth(self, cr, uid, context=None):
        auth_obj = self.pool.get('ida.app.taobao.auth')
        return auth_obj.get_auth(cr, uid, context=context)
    
    def set_auth(self, cr, uid, auth_id, context=None):
        auth_obj = self.pool.get('ida.app.taobao.auth')
        return auth_obj.set_auth(cr, uid, auth_id, context=context)
    def putaway_statistics(self, cr, uid, start_date, end_date, context=None):
        if not context:
            context = {}
        res = []
        if not isinstance(start_date, (dt)):
            try:
                start_date = dt.strptime(start_date, '%m/%d/%Y %H:%M:%S')
            except:
                print '1'
                return res
        if not isinstance(end_date, (dt)):
            try:
                end_date = dt.strptime(end_date, '%m/%d/%Y %H:%M:%S')
            except:
                print '2'
                return res
        res.append({
                    'GRTime': dt.strptime('9/1/2014 9:15:24', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/1/2014 15:27:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000256',
                    'Operator': 'Peter',
                    'PartNo': 'A2286',
                    'Quantity': 2})
        res.append({
                    'GRTime': dt.strptime('9/4/2014 12:12:20', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/5/2014 17:29:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000259',
                    'Operator': 'Peter',
                    'PartNo': 'A2286',
                    'Quantity': 2})
        res.append({
                    'GRTime': dt.strptime('9/1/2014 9:15:24', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/1/2014 15:50:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000257',
                    'Operator': 'Peter',
                    'PartNo': 'A2286',
                    'Quantity': 2})
        res.append({
                    'GRTime': dt.strptime('9/1/2014 9:15:24', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/1/2014 17:50:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000258',
                    'Operator': 'Peter',
                    'PartNo': 'A2286',
                    'Quantity': 2})
        res.append({
                    'GRTime': dt.strptime('9/1/2014 9:15:24', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/1/2014 10:20:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000251',
                    'Operator': 'Peter',
                    'PartNo': 'A2286',
                    'Quantity': 2})
        res.append({
                    'GRTime': dt.strptime('9/1/2014 9:15:24', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/1/2014 11:20:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000252',
                    'Operator': 'Peter',
                    'PartNo': 'A2286',
                    'Quantity': 2})
        res.append({
                    'GRTime': dt.strptime('9/1/2014 9:15:24', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/1/2014 11:20:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000253',
                    'Operator': 'Peter',
                    'PartNo': 'A2286',
                    'Quantity': 2})
        res.append({
                    'GRTime': dt.strptime('9/1/2014 9:15:24', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/1/2014 11:45:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000254',
                    'Operator': 'Peter',
                    'PartNo': 'A2286',
                    'Quantity': 2})
        res.append({
                    'GRTime': dt.strptime('9/1/2014 9:15:24', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/1/2014 12:45:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000255',
                    'Operator': 'Peter',
                    'PartNo': 'A2286',
                    'Quantity': 2})
        res.append({
                    'GRTime': dt.strptime('9/1/2014 9:15:24', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/1/2014 16:45:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000260',
                    'Operator': 'Peter',
                    'PartNo': 'A2286',
                    'Quantity': 4})
        res.append({
                    'GRTime': dt.strptime('9/10/2014 15:15:23', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/10/2014 16:45:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000261',
                    'Operator': 'Raymond',
                    'PartNo': 'A2512',
                    'Quantity': 10})
        res.append({
                    'GRTime': dt.strptime('9/10/2014 15:15:23', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/10/2014 17:25:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000262',
                    'Operator': 'Raymond',
                    'PartNo': 'A2512',
                    'Quantity': 10})
        res.append({
                    'GRTime': dt.strptime('9/10/2014 15:15:23', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/10/2014 20:40:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000263',
                    'Operator': 'Raymond',
                    'PartNo': 'A2512',
                    'Quantity': 10})
        res.append({
                    'GRTime': dt.strptime('9/10/2014 15:15:23', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/10/2014 19:56:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000264',
                    'Operator': 'Raymond',
                    'PartNo': 'A2512',
                    'Quantity': 10})
        res.append({
                    'GRTime': dt.strptime('9/10/2014 15:15:23', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/11/2014 9:17:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000265',
                    'Operator': 'Raymond',
                    'PartNo': 'A2512',
                    'Quantity': 10})
        res.append({
                    'GRTime': dt.strptime('9/6/2014 8:15:20', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/7/2014 13:56:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000266',
                    'Operator': 'Jack',
                    'PartNo': 'A2691',
                    'Quantity': 8})
        res.append({
                    'GRTime': dt.strptime('9/6/2014 8:15:20', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/6/2014 8:40:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000267',
                    'Operator': 'Jack',
                    'PartNo': 'A2691',
                    'Quantity': 8})
        res.append({
                    'GRTime': dt.strptime('9/6/2014 8:15:20', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/6/2014 17:20:03', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000268',
                    'Operator': 'Jack',
                    'PartNo': 'A2691',
                    'Quantity': 8})
        res.append({
                    'GRTime': dt.strptime('9/6/2014 8:15:20', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/6/2014 15:11:56', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000269',
                    'Operator': 'Jack',
                    'PartNo': 'A2691',
                    'Quantity': 8})
        res.append({
                    'GRTime': dt.strptime('9/6/2014 8:15:20', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/6/2014 20:18:51', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000270',
                    'Operator': 'Jack',
                    'PartNo': 'A2691',
                    'Quantity': 8})
        res.append({
                    'GRTime': dt.strptime('9/6/2014 8:15:20', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/6/2014 21:19:55', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000271',
                    'Operator': 'Jack',
                    'PartNo': 'A2691',
                    'Quantity': 8})
        res.append({
                    'GRTime': dt.strptime('9/6/2014 8:15:20', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/6/2014 18:49:55', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000272',
                    'Operator': 'Jack',
                    'PartNo': 'A2691',
                    'Quantity': 8})
        res.append({
                    'GRTime': dt.strptime('9/4/2014 11:05:11', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/4/2014 12:40:55', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000273',
                    'Operator': 'Howard',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        res.append({
                    'GRTime': dt.strptime('9/4/2014 11:05:11', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/4/2014 15:20:55', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000274',
                    'Operator': 'Howard',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        res.append({
                    'GRTime': dt.strptime('9/4/2014 11:05:11', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/4/2014 15:27:55', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000275',
                    'Operator': 'Howard',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        res.append({
                    'GRTime': dt.strptime('9/4/2014 11:05:11', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/4/2014 18:33:55', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000276',
                    'Operator': 'Howard',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        res.append({
                    'GRTime': dt.strptime('9/8/2014 10:45:03', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/8/2014 12:00:05', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000277',
                    'Operator': 'Philip',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        res.append({
                    'GRTime': dt.strptime('9/8/2014 10:45:03', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/8/2014 13:09:26', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000278',
                    'Operator': 'Philip',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        res.append({
                    'GRTime': dt.strptime('9/8/2014 10:45:03', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/8/2014 13:09:26', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000279',
                    'Operator': 'Philip',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        res.append({
                    'GRTime': dt.strptime('9/8/2014 10:45:03', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/8/2014 13:09:26', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000280',
                    'Operator': 'Philip',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        res.append({
                    'GRTime': dt.strptime('9/8/2014 10:45:03', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/8/2014 15:20:08', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000281',
                    'Operator': 'Philip',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        res.append({
                    'GRTime': dt.strptime('9/8/2014 10:45:03', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/8/2014 15:51:08', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000282',
                    'Operator': 'Philip',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        res.append({
                    'GRTime': dt.strptime('9/8/2014 10:45:03', '%m/%d/%Y %H:%M:%S'), 
                    'PutawayTime': dt.strptime('9/8/2014 17:30:00', '%m/%d/%Y %H:%M:%S'),
                    'PackageNo': 'Q0000283',
                    'Operator': 'Philip',
                    'PartNo': 'A2677',
                    'Quantity': 5})
        return res
    def activate_product(self, cr, uid, product_code, mac_id, context=None):
        if not context:
            context = {}
        if not product_code or not mac_id:
            return {'Code': 0, 'Msg': 'Please pass in Product Code and MAC ID!'}
        lic_obj = self.pool.get('ida.app.license')
        lic_domain = [('product_code', '=', product_code)]
        lic_ids = lic_obj.search(cr, SUPERUSER_ID, lic_domain, context=context)
        if lic_ids:
            if isinstance(lic_ids, (int, long)):
                lic_ids = [lic_ids]
            lic = lic_obj.browse(cr, SUPERUSER_ID, lic_ids, context=context)[0]
            if not lic.mac_id:
                lic_obj.write(cr, SUPERUSER_ID, lic_ids[0], {'mac_id': mac_id, 'is_active': True}, context=context)
            else:
                if lic.mac_id == mac_id:
                    lic_obj.write(cr, SUPERUSER_ID, lic_ids[0], {'is_active': True}, context=context)
                else:
                    return {'Code': 0, 'Msg': 'This Product Code has been assigned to another device already!'}
            return {'Code': 1, 'Msg': 'Success'}
        else:
            return {'Code': 0, 'Msg': 'Invalid Product Code!'}
class wms_interface(http.Controller):
    _cp_path = '/service/wms'
     
    @http.httprequest
    def getpickingin(self, req, **kwargs):
        po = req.httprequest.args['po']
        res = []
        if not po:
            return Response(json.dumps({'res': res}), 200, mimetype='application/json')
        #change to the credentials of your own
        user = 'XXX'
        pwd = 'XXX'
        dbname = 'XXX'
        ipaddress = 'XXX'
        common_url = ipaddress + '/xmlrpc/common'
        object_url = ipaddress + '/xmlrpc/object'
        sock = xmlrpclib.ServerProxy(common_url)
        uid = sock.login(dbname, user, pwd)
        sock = xmlrpclib.ServerProxy(object_url)
        
        res = sock.execute(dbname, uid, pwd, 'ida.app.framework', 'get_picking_in', po)   
        return Response(res, 200, mimetype='application/html')
    @http.httprequest
    def test(self, req, **kwargs):
        #change to the credentials of your own
        user = 'XXX'
        pwd = 'XXX'
        dbname = 'XXX'
        ipaddress = 'XXX'
        common_url = ipaddress + '/xmlrpc/common'
        object_url = ipaddress + '/xmlrpc/object'
        sock = xmlrpclib.ServerProxy(common_url)
        uid = sock.login(dbname, user, pwd)
        sock = xmlrpclib.ServerProxy(object_url)
        
        res = sock.execute(dbname, uid, pwd, 'ida.app.framework', 'sync_product')   
        return Response(json.dumps(res), 200, mimetype='application/json')
    @http.httprequest
    def goodsreceiving(self, req, **kwargs):
        res = []
        #change to the credentials of your own
        user = 'XXX'
        pwd = 'XXX'
        dbname = 'XXX'
        ipaddress = 'XXX'
        common_url = ipaddress + '/xmlrpc/common'
        object_url = ipaddress + '/xmlrpc/object'
        sock = xmlrpclib.ServerProxy(common_url)
        uid = sock.login(dbname, user, pwd)
        sock = xmlrpclib.ServerProxy(object_url)
        
        res = sock.execute(dbname, uid, pwd, 'ida.app.framework', 'goods_receiving', '', '')   
        return Response(json.dumps(res), 200, mimetype='application/json')
    
    @http.httprequest
    def getpickingout(self, req, **kwargs):
        so = req.httprequest.args['so']
        res = []
        if not so:
            return Response(json.dumps({'res': res}), 200, mimetype='application/json')
        #change to the credentials of your own
        user = 'XXX'
        pwd = 'XXX'
        dbname = 'XXX'
        ipaddress = 'XXX'
        common_url = ipaddress + '/xmlrpc/common'
        object_url = ipaddress + '/xmlrpc/object'
        sock = xmlrpclib.ServerProxy(common_url)
        uid = sock.login(dbname, user, pwd)
        sock = xmlrpclib.ServerProxy(object_url)
        
        res = sock.execute(dbname, uid, pwd, 'ida.app.framework', 'get_picking_out', so)   
        return Response(json.dumps(res), 200, mimetype='application/json')
    
    @http.httprequest
    def cyclecount(self, req, **kwargs):
        stock = json.loads(req.httprequest.data)
        #change to the credentials of your own
        user = 'XXX'
        pwd = 'XXX'
        dbname = 'XXX'
        ipaddress = 'XXX'
        common_url = ipaddress + '/xmlrpc/common'
        object_url = ipaddress + '/xmlrpc/object'
        sock = xmlrpclib.ServerProxy(common_url)
        uid = sock.login(dbname, user, pwd)
        sock = xmlrpclib.ServerProxy(object_url)
        
        res = sock.execute(dbname, uid, pwd, 'ida.app.framework', 'cycle_count', stock)   
        return Response(json.dumps(res), 200, mimetype='application/json')
    
    @http.httprequest
    def querystock(self, req, **kwargs):
        location = req.httprequest.args['location']
        material = req.httprequest.args['material']
        res = []
        #change to the credentials of your own
        user = 'XXX'
        pwd = 'XXX'
        dbname = 'XXX'
        ipaddress = 'XXX'
        common_url = ipaddress + '/xmlrpc/common'
        object_url = ipaddress + '/xmlrpc/object'
        sock = xmlrpclib.ServerProxy(common_url)
        uid = sock.login(dbname, user, pwd)
        sock = xmlrpclib.ServerProxy(object_url)
        
        res = sock.execute(dbname, uid, pwd, 'ida.app.framework', 'query_stock', location, material)   
        return Response(json.dumps(res), 200, mimetype='application/json')
        
         
         