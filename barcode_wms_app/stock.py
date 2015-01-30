from datetime import datetime
from dateutil.relativedelta import relativedelta
import time
from operator import itemgetter
from itertools import groupby

from openerp.osv import fields, osv, orm
from openerp.tools.translate import _
from openerp import netsvc
from openerp import tools
from openerp.tools import float_compare, DEFAULT_SERVER_DATETIME_FORMAT
import openerp.addons.decimal_precision as dp
import logging
import binascii
import base64
import os
from config import CONFIG_OBJ
from fedex.services.ship_service import FedexProcessShipmentRequest
_logger = logging.getLogger(__name__)


class stock_partial_picking(osv.osv_memory):
    _name = 'stock.partial.picking'
    _inherit = 'stock.partial.picking'
    
    def do_partial(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        assert len(ids) == 1, 'Partial picking processing may only be done one at a time.'
        stock_picking = self.pool.get('stock.picking')
        stock_move = self.pool.get('stock.move')
        uom_obj = self.pool.get('product.uom')
        partial = self.browse(cr, uid, ids[0], context=context)
        partial_data = {
            'delivery_date' : partial.date
        }
        picking_type = partial.picking_id.type
        for wizard_line in partial.move_ids:
            line_uom = wizard_line.product_uom
            move_id = wizard_line.move_id.id

            #Quantiny must be Positive
            if wizard_line.quantity < 0:
                raise osv.except_osv(_('Warning!'), _('Please provide proper Quantity.'))

            #Compute the quantity for respective wizard_line in the line uom (this jsut do the rounding if necessary)
            qty_in_line_uom = uom_obj._compute_qty(cr, uid, line_uom.id, wizard_line.quantity, line_uom.id)

            if line_uom.factor and line_uom.factor <> 0:
                if float_compare(qty_in_line_uom, wizard_line.quantity, precision_rounding=line_uom.rounding) != 0:
                    raise osv.except_osv(_('Warning!'), _('The unit of measure rounding does not allow you to ship "%s %s", only rounding of "%s %s" is accepted by the Unit of Measure.') % (wizard_line.quantity, line_uom.name, line_uom.rounding, line_uom.name))
            if move_id:
                #Check rounding Quantity.ex.
                #picking: 1kg, uom kg rounding = 0.01 (rounding to 10g),
                #partial delivery: 253g
                #=> result= refused, as the qty left on picking would be 0.747kg and only 0.75 is accepted by the uom.
                initial_uom = wizard_line.move_id.product_uom
                #Compute the quantity for respective wizard_line in the initial uom
                qty_in_initial_uom = uom_obj._compute_qty(cr, uid, line_uom.id, wizard_line.quantity, initial_uom.id)
                without_rounding_qty = (wizard_line.quantity / line_uom.factor) * initial_uom.factor
                if float_compare(qty_in_initial_uom, without_rounding_qty, precision_rounding=initial_uom.rounding) != 0:
                    raise osv.except_osv(_('Warning!'), _('The rounding of the initial uom does not allow you to ship "%s %s", as it would let a quantity of "%s %s" to ship and only rounding of "%s %s" is accepted by the uom.') % (wizard_line.quantity, line_uom.name, wizard_line.move_id.product_qty - without_rounding_qty, initial_uom.name, initial_uom.rounding, initial_uom.name))
            else:
                seq_obj_name =  'stock.picking.' + picking_type
                move_id = stock_move.create(cr,uid,{'name' : self.pool.get('ir.sequence').get(cr, uid, seq_obj_name),
                                                    'product_id': wizard_line.product_id.id,
                                                    'product_qty': wizard_line.quantity,
                                                    'product_uom': wizard_line.product_uom.id,
                                                    'prodlot_id': wizard_line.prodlot_id.id,
                                                    'location_id' : wizard_line.location_id.id,
                                                    'location_dest_id' : wizard_line.location_dest_id.id,
                                                    'picking_id': partial.picking_id.id
                                                    },context=context)
                stock_move.action_confirm(cr, uid, [move_id], context)
            partial_data['move%s' % (move_id)] = {
                'product_id': wizard_line.product_id.id,
                'product_qty': wizard_line.quantity,
                'product_uom': wizard_line.product_uom.id,
                'prodlot_id': wizard_line.prodlot_id.id,
            }
            if (picking_type == 'in') and (wizard_line.product_id.cost_method == 'average'):
                partial_data['move%s' % (wizard_line.move_id.id)].update(product_price=wizard_line.cost,
                                                                  product_currency=wizard_line.currency.id)
        
        # Do the partial delivery and open the picking that was delivered
        # We don't need to find which view is required, stock.picking does it.
        done = stock_picking.do_partial(
            cr, uid, [partial.picking_id.id], partial_data, context=context)
        
        
        picking = self.pool.get('stock.picking.out').read(cr, uid, done[partial.picking_id.id]['delivered_picking'], ['origin', 'name'], context)
        so = picking['origin']
        # Set this to the INFO level to see the response from Fedex printed in stdout.
        logging.basicConfig(level=logging.INFO)
        
        # This is the object that will be handling our tracking request.
        # We're using the FedexConfig object from example_config.py in this dir.
        shipment = FedexProcessShipmentRequest(CONFIG_OBJ, customer_transaction_id='ProcessShipmentRequest_v15')
        
        # This is very generalized, top-level information.
        # REGULAR_PICKUP, REQUEST_COURIER, DROP_BOX, BUSINESS_SERVICE_CENTER or STATION
        shipment.RequestedShipment.DropoffType = 'REGULAR_PICKUP'
        
        # See page 355 in WS_ShipService.pdf for a full list. Here are the common ones:
        # STANDARD_OVERNIGHT, PRIORITY_OVERNIGHT, FEDEX_GROUND, FEDEX_EXPRESS_SAVER
        shipment.RequestedShipment.ServiceType = 'FEDEX_GROUND'
        
        # What kind of package this will be shipped in.
        # FEDEX_BOX, FEDEX_PAK, FEDEX_TUBE, YOUR_PACKAGING
        shipment.RequestedShipment.PackagingType = 'YOUR_PACKAGING'
        shipment.RequestedShipment.PreferredCurrency = 'USD'
        
        # Shipper contact info.
        shipment.RequestedShipment.Shipper.Contact.PersonName = 'Sam'
        shipment.RequestedShipment.Shipper.Contact.CompanyName = 'Cute Shoe'
        shipment.RequestedShipment.Shipper.Contact.PhoneNumber = '9012638716'
        shipment.RequestedShipment.Shipper.Contact.EMailAddress = 'info@cuteshoe.com'
        
        # Shipper address.
        shipment.RequestedShipment.Shipper.Address.StreetLines = ['2000 Freight LTL Testing', 'Do Not Delete - Test Account']
        shipment.RequestedShipment.Shipper.Address.City = 'Harrison'
        shipment.RequestedShipment.Shipper.Address.StateOrProvinceCode = 'AR'
        shipment.RequestedShipment.Shipper.Address.PostalCode = '72601'
        shipment.RequestedShipment.Shipper.Address.CountryCode = 'US'
        #shipment.RequestedShipment.Shipper.Address.Residential = True
        
        # Recipient contact info.
        shipment.RequestedShipment.Recipient.Contact.PersonName = 'Jack'
        shipment.RequestedShipment.Recipient.Contact.CompanyName = 'Taobao'
        shipment.RequestedShipment.Recipient.Contact.PhoneNumber = '9012637906'
        shipment.RequestedShipment.Recipient.Contact.EMailAddress = 'info@taobao.com'
        
        # Recipient address
        shipment.RequestedShipment.Recipient.Address.StreetLines = ['1202 Chalet Ln', 'Do Not Delete - Test Account']
        shipment.RequestedShipment.Recipient.Address.City = 'Harrison'
        shipment.RequestedShipment.Recipient.Address.StateOrProvinceCode = 'AR'
        shipment.RequestedShipment.Recipient.Address.PostalCode = '72601'
        shipment.RequestedShipment.Recipient.Address.CountryCode = 'US'
        # This is needed to ensure an accurate rate quote with the response.
        #shipment.RequestedShipment.Recipient.Address.Residential = True
        shipment.RequestedShipment.EdtRequestType = 'NONE'
        #shipment.RequestedShipment.CustomsClearanceDetail.ClearanceBrokerage = 'BROKER_UNASSIGNED'
        #shipment.RequestedShipment.CustomsClearanceDetail.DocumentContent = 'DOCUMENTS_ONLY'
        #shipment.RequestedShipment.CustomsClearanceDetail.CustomsValue.Currency = 'USD'
        #shipment.RequestedShipment.CustomsClearanceDetail.CustomsValue.Amount = 100
        #shipment.RequestedShipment.CustomsClearanceDetail.FreightOnValue = 'CARRIER_RISK'
        
        shipment.RequestedShipment.ShippingChargesPayment.Payor.ResponsibleParty.AccountNumber = CONFIG_OBJ.account_number
        shipment.RequestedShipment.ShippingChargesPayment.Payor.ResponsibleParty.Tins = [{'TinType': 'BUSINESS_STATE', 'Number': '353'}]
        shipment.RequestedShipment.ShippingChargesPayment.Payor.ResponsibleParty.Contact = [{'ContactId': '12345', 'PersonName': 'jack'}]
        # Who pays for the shipment?
        # RECIPIENT, SENDER or THIRD_PARTY
        shipment.RequestedShipment.ShippingChargesPayment.PaymentType = 'SENDER' 
        
        # Specifies the label type to be returned.
        # LABEL_DATA_ONLY or COMMON2D
        shipment.RequestedShipment.LabelSpecification.LabelFormatType = 'COMMON2D'
        
        # Specifies which format the label file will be sent to you in.
        # DPL, EPL2, PDF, PNG, ZPLII
        shipment.RequestedShipment.LabelSpecification.ImageType = 'PNG'
        
        # To use doctab stocks, you must change ImageType above to one of the
        # label printer formats (ZPLII, EPL2, DPL).
        # See documentation for paper types, there quite a few.
        shipment.RequestedShipment.LabelSpecification.LabelStockType = 'PAPER_4X6'
        
        # This indicates if the top or bottom of the label comes out of the 
        # printer first.
        # BOTTOM_EDGE_OF_TEXT_FIRST or TOP_EDGE_OF_TEXT_FIRST
        shipment.RequestedShipment.LabelSpecification.LabelPrintingOrientation = 'BOTTOM_EDGE_OF_TEXT_FIRST'
        shipment.RequestedShipment.LabelSpecification.LabelOrder = 'SHIPPING_LABEL_FIRST'
        
        package1_weight = shipment.create_wsdl_object_of_type('Weight')
        # Weight, in pounds.
        package1_weight.Value = 1.0
        package1_weight.Units = "LB"
        
        package1_dim = shipment.create_wsdl_object_of_type('Dimensions')
        package1_dim.Length = 12
        package1_dim.Width = 12
        package1_dim.Height = 12
        package1_dim.Units = 'IN'
        
        
        
        package1 = shipment.create_wsdl_object_of_type('RequestedPackageLineItem')
        package1.PhysicalPackaging = 'BOX'
        package1.Weight = package1_weight
        package1.SequenceNumber = 1
        package1.Dimensions = package1_dim
        package1.CustomerReferences = [{'CustomerReferenceType': 'CUSTOMER_REFERENCE', 'Value': so}]
        # Un-comment this to see the other variables you may set on a package.
        #print package1
        
        # This adds the RequestedPackageLineItem WSDL object to the shipment. It
        # increments the package count and total weight of the shipment for you.
        shipment.client.wsdl.services[0].setlocation('https://wsbeta.fedex.com:443/web-services/ship')
        logging.basicConfig(level=logging.INFO)
        logging.getLogger('suds.client').setLevel(logging.DEBUG)
        logging.getLogger('suds.transport').setLevel(logging.DEBUG)
        logging.getLogger('suds.xsd.schema').setLevel(logging.DEBUG)
        logging.getLogger('suds.wsdl').setLevel(logging.DEBUG)
        shipment.add_package(package1)
        
        # If you'd like to see some documentation on the ship service WSDL, un-comment
        # this line. (Spammy).
        #print shipment.client
        
        # Un-comment this to see your complete, ready-to-send request as it stands
        # before it is actually sent. This is useful for seeing what values you can
        # change.
        #print shipment.RequestedShipment
        
        # If you want to make sure that all of your entered details are valid, you
        # can call this and parse it just like you would via send_request(). If
        # shipment.response.HighestSeverity == "SUCCESS", your shipment is valid.
        #shipment.send_validation_request()
        
        # Fires off the request, sets the 'response' attribute on the object.
        shipment.send_request()
        
        # This will show the reply to your shipment being sent. You can access the
        # attributes through the response attribute on the request object. This is
        # good to un-comment to see the variables returned by the Fedex reply.
        print shipment.response
        
        # Here is the overall end result of the query.
        print "HighestSeverity:", shipment.response.HighestSeverity
        # Getting the tracking number from the new shipment.
        print "Tracking #:", shipment.response.CompletedShipmentDetail.CompletedPackageDetails[0].TrackingIds[0].TrackingNumber
        # Net shipping costs.
        print "Net Shipping Cost (US$):", shipment.response.CompletedShipmentDetail.CompletedPackageDetails[0].PackageRating.PackageRateDetails[0].NetCharge.Amount
        
        # Get the label image in ASCII format from the reply. Note the list indices
        # we're using. You'll need to adjust or iterate through these if your shipment
        # has multiple packages.
        ascii_label_data = shipment.response.CompletedShipmentDetail.CompletedPackageDetails[0].Label.Parts[0].Image
        # Convert the ASCII data to binary.
        label_binary_data = binascii.a2b_base64(ascii_label_data)
        
        """
        This is an example of how to dump a label to a PNG file.
        """
        # This will be the file we write the label out to.
        png_file = open(os.path.dirname(os.path.abspath(__file__)) + '/static/' + picking['name'].replace('/', '') + '.png', 'wb')
        png_file.write(label_binary_data)
        png_file.close()
#         label = open(os.path.dirname(os.path.abspath(__file__)) + '/' + picking['name'].replace('/', '') + '.png', 'rU')
#         label_data = label.read()
#         label_binary_data = base64.b64encode(label_data)
        vals = {
                'courier_label': '/ida_wms_app/static/' + picking['name'].replace('/', '') + '.png'
                }
        self.pool.get('stock.picking.out').write(cr, uid, done[partial.picking_id.id]['delivered_picking'], vals, context)
        """
        This is an example of how to print the label to a serial printer. This will not
        work for all label printers, consult your printer's documentation for more
        details on what formats it can accept.
        """
        # Pipe the binary directly to the label printer. Works under Linux
        # without requiring PySerial. This WILL NOT work on other platforms.
        #label_printer = open("/dev/ttyS0", "w")
        #label_printer.write(label_binary_data)
        #label_printer.close()
        
        """
        This is a potential cross-platform solution using pySerial. This has not been
        tested in a long time and may or may not work. For Windows, Mac, and other
        platforms, you may want to go this route.
        """
        #import serial
        #label_printer = serial.Serial(0)
        #print "SELECTED SERIAL PORT: "+ label_printer.portstr
        #label_printer.write(label_binary_data)
        #label_printer.close()
        
        if done[partial.picking_id.id]['delivered_picking'] == partial.picking_id.id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'res_model': context.get('active_model', 'stock.picking'),
            'name': _('Partial Delivery'),
            'res_id': done[partial.picking_id.id]['delivered_picking'],
            'view_type': 'form',
            'view_mode': 'form,tree,calendar',
            'context': context,
        }
        
        
class stock_picking_out(osv.osv):
    _name = 'stock.picking.out'
    _inherit = 'stock.picking.out'
    _table = "stock_picking"
    
    _columns = {
                'courier_label': fields.char('Courier Label', select=True),
                }
    def read(self, cr, uid, ids, fields=None, context=None, load='_classic_read'):
        res = super(stock_picking_out, self).read(cr, uid, ids, fields=fields, context=context, load=load)
        if not isinstance(res, (list, )):
            cr.execute('select courier_label from stock_picking where id=%s' % (res['id'], ))
            res['courier_label'] = cr.fetchone()[0]
        else:
            for item in res:
                cr.execute('select courier_label from stock_picking where id=%s' % (item['id'], ))
                item['courier_label'] = cr.fetchone()[0]
        return res
    
    def view_courier_label(self, cr, uid, ids, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        res = self.read(cr, uid, ids, ['courier_label'], context=context)[0]
        if not res['courier_label']:
            return
        base_url = self.pool.get('ir.config_parameter').get_param(cr, uid, 'web.base.url')
        return {'type': 'ir.actions.act_url', 'url': base_url + res['courier_label'], 'target': 'new'}
    
    
    