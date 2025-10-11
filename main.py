# main.py - API Python simple pour scraping ERAC

from flask import Flask, jsonify
import requests
from bs4 import BeautifulSoup
import os

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "service": "ERAC Scraper API",
        "status": "running",
        "endpoints": {
            "/scrape": "GET - Lance le scraping ERAC"
        }
    })

@app.route('/scrape')
def scrape_erac():
    try:
        # Votre code Pipedream exact
        session = requests.Session()

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        }

        # Page de login
        login_page_response = session.get('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', headers=headers)
        login_page_soup = BeautifulSoup(login_page_response.text, 'html.parser')
        token_element = login_page_soup.find('input', {'name': '__RequestVerificationToken'})
        
        if not token_element:
            raise ValueError("Unable to find __RequestVerificationToken on the login page")
        
        token = token_element['value']

        # Login
        login_payload = {
            'LoginId': os.getenv('ERAC_LOGIN_ID', 'ROUYOlivier1'),
            'Password': os.getenv('ERAC_PASSWORD', 'Parkopoly1234'),
            '__RequestVerificationToken': token,
        }
        
        login_headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        login_headers.update(headers)
        
        login_response_outbound = session.post('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', data=login_payload, headers=login_headers)
        login_response_inbound = session.post('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FInbound', data=login_payload, headers=login_headers)

        # Terms
        terms_page_response = session.get('https://erac.hkremarketing.com/vendor/scoc', headers=headers)
        terms_page_soup = BeautifulSoup(terms_page_response.text, 'html.parser')

        token_element = terms_page_soup.find('input', {'name': '__RequestVerificationToken'})
        if token_element:
            token = token_element['value']
            accept_payload = {
                'action': 'agree',
                '__RequestVerificationToken': token,
            }
        else:
            accept_payload = {
                'action': 'agree',
            }

        accept_headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        accept_headers.update(headers)
        accept_response = session.post('https://erac.hkremarketing.com/vendor/scoc', data=accept_payload, headers=accept_headers)

        # AJAX Data
        ajax_headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
        }
        ajax_headers.update(headers)
        
        # Payload Outbound
        ajax_payload_outbound = {
            'draw': 2,
            'columns[0][data]': 'GroupCode',
            'columns[0][name]': '',
            'columns[0][searchable]': 'true',
            'columns[0][orderable]': 'true',
            'columns[0][search][value]': '',
            'columns[0][search][regex]': 'false',
            'columns[1][data]': 'RegNo',
            'columns[1][name]': '',
            'columns[1][searchable]': 'true',
            'columns[1][orderable]': 'true',
            'columns[1][search][value]': '',
            'columns[1][search][regex]': 'false',
            'columns[2][data]': 'UnitNo',
            'columns[2][name]': '',
            'columns[2][searchable]': 'true',
            'columns[2][orderable]': 'true',
            'columns[2][search][value]': '',
            'columns[2][search][regex]': 'false',
            'columns[3][data]': 'MakeModel',
            'columns[3][name]': '',
            'columns[3][searchable]': 'true',
            'columns[3][orderable]': 'true',
            'columns[3][search][value]': '',
            'columns[3][search][regex]': 'false',
            'columns[4][data]': 'DeliveryCharge',
            'columns[4][name]': '',
            'columns[4][searchable]': 'true',
            'columns[4][orderable]': 'true',
            'columns[4][search][value]': '',
            'columns[4][search][regex]': 'false',
            'columns[5][data]': 'AllocationDate',
            'columns[5][name]': '',
            'columns[5][searchable]': 'true',
            'columns[5][orderable]': 'true',
            'columns[5][search][value]': '',
            'columns[5][search][regex]': 'false',
            'columns[6][data]': 'AllocationDateTicks',
            'columns[6][name]': '',
            'columns[6][searchable]': 'true',
            'columns[6][orderable]': 'true',
            'columns[6][search][value]': '',
            'columns[6][search][regex]': 'false',
            'columns[7][data]': 'CollectionAddress',
            'columns[7][name]': '',
            'columns[7][searchable]': 'true',
            'columns[7][orderable]': 'true',
            'columns[7][search][value]': '',
            'columns[7][search][regex]': 'false',
            'columns[8][data]': 'ExpectedDeliveryDate',
            'columns[8][name]': '',
            'columns[8][searchable]': 'true',
            'columns[8][orderable]': 'true',
            'columns[8][search][value]': '',
            'columns[8][search][regex]': 'false',
            'columns[9][data]': 'ExpectedDeliveryDateTicks',
            'columns[9][name]': '',
            'columns[9][searchable]': 'true',
            'columns[9][orderable]': 'true',
            'columns[9][search][value]': '',
            'columns[9][search][regex]': 'false',
            'columns[10][data]': 'DeliveryAddress',
            'columns[10][name]': '',
            'columns[10][searchable]': 'true',
            'columns[10][orderable]': 'true',
            'columns[10][search][value]': '',
            'columns[10][search][regex]': 'false',
            'order[0][column]': 0,
            'order[0][dir]': 'asc',
            'start': 0,
            'length': 500,
            'search[value]': '',
            'search[regex]': 'false',
            'Code': 'outbound',
            'MovementType': 'collections',
            'RegNo': '',
            'CollectionDateFrom': '',
            'CollectionDateTo': '',
            'CollectionPostcode': '',
            'DeliveryDateFrom': '',
            'DeliveryDateTo': '',
            'DeliveryPostcode': '',
            'CreatedDateFrom': '',
            'CreatedDateTo': '',
            'ReleaseCode': ''
        }
        
        # Payload Inbound (même structure, juste Code = 'inbound')
        ajax_payload_inbound = ajax_payload_outbound.copy()
        ajax_payload_inbound['Code'] = 'inbound'
        
        # Requêtes AJAX
        ajax_response_inbound = session.post('https://erac.hkremarketing.com/Vendor/AjaxSearch', data=ajax_payload_inbound, headers=ajax_headers)
        ajax_response_outbound = session.post('https://erac.hkremarketing.com/Vendor/AjaxSearch', data=ajax_payload_outbound, headers=ajax_headers)

        # Données
        data_inbound = ajax_response_inbound.json()
        data_outbound = ajax_response_outbound.json()
        
        combined_data = {
            'inbound': data_inbound['data'],
            'outbound': data_outbound['data'],
            'total_inbound': len(data_inbound['data']),
            'total_outbound': len(data_outbound['data'])
        }
        
        return jsonify({
            'success': True,
            'data': combined_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
