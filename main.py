# main.py - API Python complète pour scraping ERAC sur Railway
# SÉCURISÉ: Credentials en variables d'environnement
# V3.0 - Ajout du scraping InTender (offres ouvertes au bidding)

from flask import Flask, jsonify
import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime
import time
import re

app = Flask(__name__)

@app.route('/')
def home():
    """Page d'accueil de l'API"""
    return jsonify({
        "service": "ERAC Scraper API",
        "status": "running",
        "version": "3.0",
        "endpoints": {
            "/": "GET - Informations de l'API",
            "/scrape/france": "GET - Scraping ERAC France (avec VIN)",
            "/scrape/germany": "GET - Scraping ERAC Germany (avec VIN)",
            "/scrape/germany/tenders": "GET - Scraping InTender Germany (offres à bidder)",
            "/scrape/france/tenders": "GET - Scraping InTender France (offres à bidder)",
            "/health": "GET - Status de santé",
            "/debug/movement/{id}": "GET - Debug d'un mouvement spécifique"
        },
        "description": "API pour scraper les données ERAC France et Germany avec détails voiture + InTender"
    })

@app.route('/health')
def health():
    """Endpoint de santé"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "ERAC Scraper API"
    })


# ============================================================
# FONCTIONS EXISTANTES - MISSIONS (INBOUND/OUTBOUND)
# ============================================================

def get_mission_details(session, movement_id, country="france", headers=None, debug=False):
    """Récupère les détails d'une mission (VIN, infos voiture, etc.)"""
    try:
        movement_url = f'https://erac.hkremarketing.com/movement/{movement_id}'
        
        if headers is None:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
            }
        
        response = session.get(movement_url, headers=headers)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # === DEBUG: Sauvegarder le HTML pour inspection ===
            if debug:
                debug_file = f'/tmp/movement_debug_{movement_id}.html'
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"🔍 HTML sauvegardé: {debug_file}")
            
            # Structure de base pour stocker les infos
            movement_data = {
                'movement_id': movement_id,
                'vin': None,
                'make_model': None,
                'registration': None,
                'unit_no': None,
                'collection_date': None,
                'delivery_date': None,
                'collection_address': None,
                'delivery_address': None,
                'collection_address_full': {
                    'name': None,
                    'address': None,
                    'tel': None,
                    'email': None
                },
                'delivery_address_full': {
                    'name': None,
                    'address': None,
                    'tel': None,
                    'email': None
                },
                'status': None,
                'delivery_charge': None,
                'error': None
            }
            
            # === CHERCHER LE VIN - Stratégie agressive ===
            # 1. Chercher le label "VIN" puis prendre la valeur qui suit
            labels = soup.find_all('label', class_='control-label')
            for label in labels:
                if 'VIN' in label.get_text().upper():
                    parent = label.parent
                    vin_element = parent.find('p', class_='form-control-static')
                    if vin_element:
                        movement_data['vin'] = vin_element.get_text().strip()
                        if debug: print(f"   ✓ VIN trouvé via label: {movement_data['vin']}")
                        break
            
            # 2. Si pas trouvé, chercher tous les p.form-control-static après un label VIN
            if not movement_data['vin']:
                all_labels = soup.find_all('label')
                for label in all_labels:
                    label_text = label.get_text().strip().upper()
                    if 'VIN' in label_text:
                        next_elem = label.find_next('p', class_='form-control-static')
                        if next_elem:
                            movement_data['vin'] = next_elem.get_text().strip()
                            if debug: print(f"   ✓ VIN trouvé via label+next: {movement_data['vin']}")
                            break
            
            # 3. Chercher directement un p.form-control-static qui contient un VIN (17 caractères)
            if not movement_data['vin']:
                all_form_statics = soup.find_all('p', class_='form-control-static')
                if debug: print(f"   → Total p.form-control-static trouvés: {len(all_form_statics)}")
                for elem in all_form_statics:
                    text = elem.get_text().strip().upper()
                    if len(text) == 17 and text[0] in 'ZWVJLMRSTUX123456789':
                        movement_data['vin'] = text
                        if debug: print(f"   ✓ VIN trouvé via form-control-static: {text}")
                        break
                    if debug and text:
                        print(f"   → p.form-control-static: {text[:50]}")
            
            # 4. Input avec id="Vin" (fallback)
            if not movement_data['vin']:
                vin_element = soup.find('input', {'id': 'Vin'})
                if vin_element:
                    movement_data['vin'] = vin_element.get('value', '').strip()
                    if debug: print(f"   ✓ VIN trouvé via id='Vin': {movement_data['vin']}")
            
            # 5. Input avec name="Vin" (fallback)
            if not movement_data['vin']:
                vin_element = soup.find('input', {'name': 'Vin'})
                if vin_element:
                    movement_data['vin'] = vin_element.get('value', '').strip()
                    if debug: print(f"   ✓ VIN trouvé via name='Vin': {movement_data['vin']}")
            
            # === CHERCHER REGISTRATION ===
            reg_element = soup.find('input', {'id': 'RegNo'}) or soup.find('input', {'name': 'RegNo'})
            if not reg_element:
                labels = soup.find_all('label')
                for label in labels:
                    if 'RegNo' in label.get_text() or 'Reg No' in label.get_text() or 'Registration' in label.get_text():
                        parent = label.parent
                        elem = parent.find('p', class_='form-control-static')
                        if elem:
                            movement_data['registration'] = elem.get_text().strip()
                            break
            else:
                movement_data['registration'] = reg_element.get('value', '').strip()
            
            # === CHERCHER MAKE/MODEL ===
            make_element = soup.find('input', {'id': 'MakeModel'}) or soup.find('input', {'name': 'MakeModel'})
            if not make_element:
                labels = soup.find_all('label')
                for label in labels:
                    label_text = label.get_text()
                    if 'Make' in label_text or 'Model' in label_text:
                        parent = label.parent
                        elem = parent.find('p', class_='form-control-static')
                        if elem:
                            movement_data['make_model'] = elem.get_text().strip()
                            break
            else:
                movement_data['make_model'] = make_element.get('value', '').strip()
            
            # === CHERCHER UNIT NO ===
            unit_element = soup.find('input', {'id': 'UnitNo'}) or soup.find('input', {'name': 'UnitNo'})
            if not unit_element:
                labels = soup.find_all('label')
                for label in labels:
                    if 'Unit' in label.get_text():
                        parent = label.parent
                        elem = parent.find('p', class_='form-control-static')
                        if elem:
                            movement_data['unit_no'] = elem.get_text().strip()
                            break
            else:
                movement_data['unit_no'] = unit_element.get('value', '').strip()
            
            # === CHERCHER DATES ===
            collection_date_element = soup.find('input', {'id': 'CollectionDate'}) or soup.find('input', {'name': 'CollectionDate'})
            if collection_date_element:
                movement_data['collection_date'] = collection_date_element.get('value', '').strip()
            
            delivery_date_element = soup.find('input', {'id': 'DeliveryDate'}) or soup.find('input', {'name': 'DeliveryDate'})
            if delivery_date_element:
                movement_data['delivery_date'] = delivery_date_element.get('value', '').strip()
            
            # === CHERCHER ADRESSES COMPLÈTES (avec tel et email) ===
            # Collection Address
            collection_data = {
                'name': None,
                'address': None,
                'tel': None,
                'email': None
            }
            
            collection_h2 = soup.find('h2', string='Collection Address')
            if collection_h2:
                parent_div = collection_h2.find_next()
                if parent_div:
                    h4_elements = parent_div.parent.find_all('h4', limit=2)
                    if len(h4_elements) >= 1:
                        name_text = h4_elements[0].get_text().strip()
                        match = re.search(r'\(([^)]+)\)', name_text)
                        code = match.group(1) if match else ''
                        collection_data['name'] = name_text.replace(f'({code})', '').strip() if code else name_text
                    
                    if len(h4_elements) >= 2:
                        collection_data['address'] = h4_elements[1].get_text().strip()
                    
                    current = h4_elements[-1] if h4_elements else parent_div
                    for elem in current.find_all_next():
                        if elem.name in ['h2', 'h1']:
                            break
                        
                        text = elem.get_text().strip()
                        if text.startswith('Tel No.'):
                            tel_match = re.search(r'Tel No\.:\s*([\d\s/\-]+)', text)
                            if tel_match:
                                collection_data['tel'] = tel_match.group(1).strip()
                        
                        if text.startswith('Email'):
                            email_match = re.search(r'Email:\s*([^\s<]+)', text)
                            if email_match:
                                collection_data['email'] = email_match.group(1).strip()
                        
                        if collection_data['tel'] and collection_data['email']:
                            break
            
            movement_data['collection_address_full'] = collection_data
            
            # === Delivery Address ===
            delivery_data = {
                'name': None,
                'address': None,
                'tel': None,
                'email': None
            }
            
            delivery_h2 = soup.find('h2', string='Delivery Address')
            if delivery_h2:
                parent_div = delivery_h2.find_next()
                if parent_div:
                    h4_elements = parent_div.parent.find_all('h4', limit=2)
                    if len(h4_elements) >= 1:
                        name_text = h4_elements[0].get_text().strip()
                        match = re.search(r'\(([^)]+)\)', name_text)
                        code = match.group(1) if match else ''
                        delivery_data['name'] = name_text.replace(f'({code})', '').strip() if code else name_text
                    
                    if len(h4_elements) >= 2:
                        delivery_data['address'] = h4_elements[1].get_text().strip()
                    
                    current = h4_elements[-1] if h4_elements else parent_div
                    for elem in current.find_all_next():
                        if elem.name in ['h2', 'h1']:
                            break
                        
                        text = elem.get_text().strip()
                        if text.startswith('Tel No.'):
                            tel_match = re.search(r'Tel No\.:\s*([\d\s/\-]+)', text)
                            if tel_match:
                                delivery_data['tel'] = tel_match.group(1).strip()
                        
                        if text.startswith('Email'):
                            email_match = re.search(r'Email:\s*([^\s<]+)', text)
                            if email_match:
                                delivery_data['email'] = email_match.group(1).strip()
                        
                        if delivery_data['tel'] and delivery_data['email']:
                            break
            
            movement_data['delivery_address_full'] = delivery_data
            
            # === CHERCHER CHARGE ===
            charge_element = soup.find('input', {'id': 'DeliveryCharge'}) or soup.find('input', {'name': 'DeliveryCharge'})
            if charge_element:
                movement_data['delivery_charge'] = charge_element.get('value', '').strip()
            
            return movement_data
            
        else:
            print(f"⚠️ HTTP {response.status_code} pour {movement_id}")
            return {
                'movement_id': movement_id, 
                'error': f'HTTP {response.status_code}'
            }
            
    except Exception as e:
        print(f"❌ Erreur parsing {movement_id}: {str(e)}")
        return {
            'movement_id': movement_id, 
            'error': str(e)
        }


def enrich_missions_with_details(session, missions, country="france", headers=None, delay=0.3):
    """Enrichit les missions avec les détails (VIN, infos voiture)"""
    enriched = []
    total = len(missions)
    
    for idx, mission in enumerate(missions):
        percent = int((idx + 1) / total * 100)
        reg_no = mission.get('RegNo', 'N/A')
        print(f"[{percent}%] {idx+1}/{total} - {reg_no}")
        
        movement_id = mission.get('Id')
        
        if movement_id:
            debug = (idx == 0)
            details = get_mission_details(session, movement_id, country, headers, debug=debug)
            enriched_mission = {**mission, **details}
            if details.get('vin'):
                print(f"     ✓ VIN trouvé: {details.get('vin')}")
            else:
                print(f"     ✗ VIN non trouvé")
        else:
            print(f"     ⚠️ Pas d'ID trouvé")
            enriched_mission = mission
        
        enriched.append(enriched_mission)
        
        if idx < total - 1:
            time.sleep(delay)
    
    print(f"✅ Enrichissement terminé: {total} missions traitées")
    return enriched


def scrape_erac_country(country="france", enrich_details=True):
    """Fonction de scraping avec credentials par pays"""
    try:
        print(f"🚀 Début du scraping ERAC {country.upper()}...")
        
        if country.lower() == "germany":
            login_id = os.getenv('ERAC_GERMANY_LOGIN')
            password = os.getenv('ERAC_GERMANY_PASSWORD')
            if not login_id or not password:
                raise ValueError("⚠️ Variables d'env manquantes: ERAC_GERMANY_LOGIN et/ou ERAC_GERMANY_PASSWORD")
            print("✓ Utilisation des credentials Germany (env vars)")
        else:
            login_id = os.getenv('ERAC_FRANCE_LOGIN')
            password = os.getenv('ERAC_FRANCE_PASSWORD')
            if not login_id or not password:
                raise ValueError("⚠️ Variables d'env manquantes: ERAC_FRANCE_LOGIN et/ou ERAC_FRANCE_PASSWORD")
            print("✓ Utilisation des credentials France (env vars)")
        
        session = requests.Session()

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        }

        # Étape 1: Page de login
        print("📄 Récupération de la page de login...")
        login_page_response = session.get(
            'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', 
            headers=headers
        )
        
        login_page_soup = BeautifulSoup(login_page_response.text, 'html.parser')
        token_element = login_page_soup.find('input', {'name': '__RequestVerificationToken'})
        
        if not token_element:
            raise ValueError("Token de vérification non trouvé - la page de login peut avoir changé")
        
        token = token_element['value']
        print("✓ Token extrait")

        # Étape 2: Login avec les credentials
        print(f"🔐 Connexion {country.upper()} en cours...")
        login_payload = {
            'LoginId': login_id,
            'Password': password,
            '__RequestVerificationToken': token,
        }
        
        login_headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        login_headers.update(headers)
        
        session.post(
            'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', 
            data=login_payload, 
            headers=login_headers
        )
        
        session.post(
            'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FInbound', 
            data=login_payload, 
            headers=login_headers
        )
        
        print(f"✓ Connexion {country.upper()} réussie")

        # Étape 3: Acceptation des conditions
        print("⚖️ Acceptation des conditions...")
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
        
        session.post(
            'https://erac.hkremarketing.com/vendor/scoc', 
            data=accept_payload, 
            headers=accept_headers
        )
        
        print("✓ Conditions acceptées")

        # Étape 4: Récupération des données AJAX
        print("📊 Récupération des données missions...")
        ajax_headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
        }
        ajax_headers.update(headers)
        
        # Payload Outbound
        ajax_payload_outbound = {
            'draw': 2,
            'columns[0][data]': 'GroupCode', 'columns[0][name]': '', 'columns[0][searchable]': 'true', 'columns[0][orderable]': 'true', 'columns[0][search][value]': '', 'columns[0][search][regex]': 'false',
            'columns[1][data]': 'RegNo', 'columns[1][name]': '', 'columns[1][searchable]': 'true', 'columns[1][orderable]': 'true', 'columns[1][search][value]': '', 'columns[1][search][regex]': 'false',
            'columns[2][data]': 'UnitNo', 'columns[2][name]': '', 'columns[2][searchable]': 'true', 'columns[2][orderable]': 'true', 'columns[2][search][value]': '', 'columns[2][search][regex]': 'false',
            'columns[3][data]': 'MakeModel', 'columns[3][name]': '', 'columns[3][searchable]': 'true', 'columns[3][orderable]': 'true', 'columns[3][search][value]': '', 'columns[3][search][regex]': 'false',
            'columns[4][data]': 'DeliveryCharge', 'columns[4][name]': '', 'columns[4][searchable]': 'true', 'columns[4][orderable]': 'true', 'columns[4][search][value]': '', 'columns[4][search][regex]': 'false',
            'columns[5][data]': 'AllocationDate', 'columns[5][name]': '', 'columns[5][searchable]': 'true', 'columns[5][orderable]': 'true', 'columns[5][search][value]': '', 'columns[5][search][regex]': 'false',
            'columns[6][data]': 'AllocationDateTicks', 'columns[6][name]': '', 'columns[6][searchable]': 'true', 'columns[6][orderable]': 'true', 'columns[6][search][value]': '', 'columns[6][search][regex]': 'false',
            'columns[7][data]': 'CollectionAddress', 'columns[7][name]': '', 'columns[7][searchable]': 'true', 'columns[7][orderable]': 'true', 'columns[7][search][value]': '', 'columns[7][search][regex]': 'false',
            'columns[8][data]': 'ExpectedDeliveryDate', 'columns[8][name]': '', 'columns[8][searchable]': 'true', 'columns[8][orderable]': 'true', 'columns[8][search][value]': '', 'columns[8][search][regex]': 'false',
            'columns[9][data]': 'ExpectedDeliveryDateTicks', 'columns[9][name]': '', 'columns[9][searchable]': 'true', 'columns[9][orderable]': 'true', 'columns[9][search][value]': '', 'columns[9][search][regex]': 'false',
            'columns[10][data]': 'DeliveryAddress', 'columns[10][name]': '', 'columns[10][searchable]': 'true', 'columns[10][orderable]': 'true', 'columns[10][search][value]': '', 'columns[10][search][regex]': 'false',
            'order[0][column]': 0, 'order[0][dir]': 'asc',
            'start': 0, 'length': 500,
            'search[value]': '', 'search[regex]': 'false',
            'Code': 'outbound', 'MovementType': 'collections',
            'RegNo': '', 'CollectionDateFrom': '', 'CollectionDateTo': '', 'CollectionPostcode': '',
            'DeliveryDateFrom': '', 'DeliveryDateTo': '', 'DeliveryPostcode': '',
            'CreatedDateFrom': '', 'CreatedDateTo': '', 'ReleaseCode': ''
        }
        
        # Payload Inbound
        ajax_payload_inbound = dict(ajax_payload_outbound)
        ajax_payload_inbound['Code'] = 'inbound'
        
        # Exécution des requêtes AJAX
        ajax_response_inbound = session.post(
            'https://erac.hkremarketing.com/Vendor/AjaxSearch', 
            data=ajax_payload_inbound, 
            headers=ajax_headers
        )
        
        ajax_response_outbound = session.post(
            'https://erac.hkremarketing.com/Vendor/AjaxSearch', 
            data=ajax_payload_outbound, 
            headers=ajax_headers
        )

        # Traitement des données
        data_inbound = ajax_response_inbound.json()
        data_outbound = ajax_response_outbound.json()
        
        if enrich_details:
            print(f"🚗 Enrichissement des données {country.upper()} avec VIN et infos voiture...")
            enriched_inbound = enrich_missions_with_details(
                session, data_inbound['data'], country, ajax_headers, delay=0.3
            )
            enriched_outbound = enrich_missions_with_details(
                session, data_outbound['data'], country, ajax_headers, delay=0.3
            )
        else:
            enriched_inbound = data_inbound['data']
            enriched_outbound = data_outbound['data']
        
        combined_data = {
            'country': country.upper(),
            'inbound': enriched_inbound,
            'outbound': enriched_outbound,
            'timestamp': datetime.utcnow().isoformat(),
            'total_inbound': len(enriched_inbound),
            'total_outbound': len(enriched_outbound),
            'records_total_inbound': data_inbound.get('recordsTotal', 0),
            'records_total_outbound': data_outbound.get('recordsTotal', 0),
            'enriched': enrich_details
        }
        
        print(f"✅ Scraping {country.upper()} réussi")
        print(f"   📤 Outbound: {combined_data['total_outbound']} missions")
        print(f"   📥 Inbound: {combined_data['total_inbound']} missions")
        
        return combined_data
        
    except Exception as e:
        print(f"❌ Erreur lors du scraping {country.upper()}: {str(e)}")
        raise


# ============================================================
# ENDPOINTS EXISTANTS - MISSIONS (INBOUND/OUTBOUND)
# ============================================================

@app.route('/scrape/france')
def scrape_france():
    """Endpoint pour le scraping ERAC France avec détails voiture"""
    try:
        data = scrape_erac_country("france", enrich_details=True)
        return jsonify({
            'success': True,
            'data': data,
            'message': f"✅ Scraping FRANCE réussi: {data['total_outbound']} véhicules outbound, {data['total_inbound']} véhicules inbound"
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'country': 'FRANCE',
            'timestamp': datetime.utcnow().isoformat(),
            'message': '❌ Erreur lors du scraping ERAC France'
        }), 500

@app.route('/scrape/germany')
def scrape_germany():
    """Endpoint pour le scraping ERAC Germany avec détails voiture"""
    try:
        data = scrape_erac_country("germany", enrich_details=True)
        return jsonify({
            'success': True,
            'data': data,
            'message': f"✅ Scraping GERMANY réussi: {data['total_outbound']} véhicules outbound, {data['total_inbound']} véhicules inbound"
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'country': 'GERMANY',
            'timestamp': datetime.utcnow().isoformat(),
            'message': '❌ Erreur lors du scraping ERAC Germany'
        }), 500

@app.route('/debug/movement/<movement_id>')
def debug_movement(movement_id):
    """Endpoint de debug pour inspecter un mouvement spécifique"""
    try:
        login_id = os.getenv('ERAC_GERMANY_LOGIN')
        password = os.getenv('ERAC_GERMANY_PASSWORD')
        
        if not login_id or not password:
            return jsonify({
                'success': False,
                'error': 'Variables d\'env manquantes: ERAC_GERMANY_LOGIN et/ou ERAC_GERMANY_PASSWORD'
            }), 500
        
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        }
        
        session = requests.Session()
        
        login_page_response = session.get(
            'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', 
            headers=headers
        )
        login_page_soup = BeautifulSoup(login_page_response.text, 'html.parser')
        token_element = login_page_soup.find('input', {'name': '__RequestVerificationToken'})
        token = token_element['value']
        
        login_payload = {
            'LoginId': login_id,
            'Password': password,
            '__RequestVerificationToken': token,
        }
        login_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        login_headers.update(headers)
        
        session.post('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', 
                    data=login_payload, headers=login_headers)
        
        details = get_mission_details(session, movement_id, "germany", headers, debug=True)
        
        return jsonify({
            'success': True,
            'movement_id': movement_id,
            'details': details,
            'message': 'Vérifiez /tmp/movement_debug_*.html pour voir le HTML complet'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================
# NOUVELLES FONCTIONS - INTENDER (OFFRES À BIDDER)
# ============================================================

def erac_login_for_tender(country="germany"):
    """
    Crée une session authentifiée sur ERAC pour InTender.
    Utilise EXACTEMENT le même flow de login que le scraper existant qui fonctionne.
    """
    if country.lower() == "germany":
        login_id = os.getenv('ERAC_GERMANY_LOGIN')
        password = os.getenv('ERAC_GERMANY_PASSWORD')
    else:
        login_id = os.getenv('ERAC_FRANCE_LOGIN')
        password = os.getenv('ERAC_FRANCE_PASSWORD')
    
    if not login_id or not password:
        raise ValueError(f"⚠️ Variables d'env manquantes pour {country.upper()}")
    
    session = requests.Session()
    
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    }
    
    # Étape 1: Login via Outbound (exactement comme le scraper existant)
    print(f"🔐 Connexion {country.upper()} (même flow que scraper existant)...")
    login_page_response = session.get(
        'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound',
        headers=headers
    )
    
    login_page_soup = BeautifulSoup(login_page_response.text, 'html.parser')
    token_element = login_page_soup.find('input', {'name': '__RequestVerificationToken'})
    
    if not token_element:
        raise ValueError("Token de vérification non trouvé - la page de login peut avoir changé")
    
    token = token_element['value']
    print("✓ Token extrait")
    
    login_payload = {
        'LoginId': login_id,
        'Password': password,
        '__RequestVerificationToken': token,
    }
    
    login_headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    login_headers.update(headers)
    
    # Double login comme le scraper existant
    session.post(
        'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound',
        data=login_payload,
        headers=login_headers
    )
    
    session.post(
        'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FInbound',
        data=login_payload,
        headers=login_headers
    )
    
    print(f"✓ Connexion {country.upper()} réussie")
    
    # Étape 2: Accepter les conditions
    print("⚖️ Acceptation des conditions...")
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
    
    session.post(
        'https://erac.hkremarketing.com/vendor/scoc',
        data=accept_payload,
        headers=accept_headers
    )
    
    print("✓ Conditions acceptées")
    
    return session, headers


def parse_tender_vehicles(html_content):
    """
    Parse le HTML de la page InTender pour extraire tous les véhicules.
    La page InTender est du HTML statique (pas AJAX).
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    vehicles = []
    
    # === METADATA DU TENDER ===
    tender_meta = {
        'end_date': None,
        'end_date_ticks': None,
        'server_time': None,
        'currency': None,
        'is_active': None,
        'on_hold': None
    }
    
    end_date_el = soup.find('input', {'id': 'EndDate'})
    if end_date_el:
        tender_meta['end_date'] = end_date_el.get('value', '').strip()
    
    end_date_ticks_el = soup.find('input', {'id': 'EndDateTicks'})
    if end_date_ticks_el:
        tender_meta['end_date_ticks'] = end_date_ticks_el.get('value', '').strip()
    
    server_ticks_el = soup.find('input', {'id': 'ServerTicks'})
    if server_ticks_el:
        tender_meta['server_time'] = server_ticks_el.get('value', '').strip()
    
    currency_el = soup.find('input', {'id': 'Currency'})
    if currency_el:
        tender_meta['currency'] = currency_el.get('value', '').strip()
    
    is_active_el = soup.find('input', {'id': 'IsActive'})
    if is_active_el:
        tender_meta['is_active'] = is_active_el.get('value', '').strip()
    
    on_hold_el = soup.find('input', {'id': 'OnHold'})
    if on_hold_el:
        tender_meta['on_hold'] = on_hold_el.get('value', '').strip()
    
    # === PARSE CHAQUE VÉHICULE ===
    table = soup.find('table', {'id': 'tblVehicles'})
    if not table:
        print("⚠️ Table #tblVehicles non trouvée")
        return {'meta': tender_meta, 'vehicles': [], 'count': 0}
    
    tbody = table.find('tbody')
    rows = tbody.find_all('tr') if tbody else []
    print(f"📋 {len(rows)} véhicules trouvés dans le tender")
    
    for idx, row in enumerate(rows):
        vehicle = parse_tender_row(row, idx)
        if vehicle:
            vehicles.append(vehicle)
    
    return {
        'meta': tender_meta,
        'vehicles': vehicles,
        'count': len(vehicles)
    }


def parse_tender_row(row, idx):
    """Parse une ligne <tr> du tableau InTender."""
    try:
        cells = row.find_all('td')
        if len(cells) < 12:
            print(f"  ⚠️ Row {idx}: pas assez de colonnes ({len(cells)})")
            return None
        
        # TENDER VEHICLE ID (hidden input)
        tender_vehicle_id_el = row.find('input', {'name': re.compile(r'Vehicles\[\d+\]\.TenderVehicleId')})
        tender_vehicle_id = tender_vehicle_id_el.get('value', '') if tender_vehicle_id_el else None
        
        # LINK MOVE
        link_move_el = cells[0].find('input')
        link_move = link_move_el.get('value', '').strip() if link_move_el else ''
        
        # MAKE MODEL
        make_model_raw = cells[1].get_text(separator=' ', strip=True)
        make_model = re.sub(r'\s+', ' ', make_model_raw).strip()
        
        make_model_parts = cells[1].decode_contents().split('<br')
        make = make_model_parts[0].strip() if len(make_model_parts) > 0 else make_model
        model = ''
        if len(make_model_parts) > 1:
            model_raw = make_model_parts[1]
            model = re.sub(r'^[/\s>]+', '', model_raw).strip()
            model = BeautifulSoup(model, 'html.parser').get_text().strip()
        
        # VEHICLE TYPE + FUEL
        vehicle_type_raw = cells[2].get_text(separator='|', strip=True)
        vehicle_type_parts = vehicle_type_raw.split('|')
        vehicle_type = vehicle_type_parts[0].strip() if len(vehicle_type_parts) > 0 else ''
        fuel_type = vehicle_type_parts[1].strip() if len(vehicle_type_parts) > 1 else ''
        
        # COLLECTION
        collection_code = cells[3].get_text(strip=True)
        collection_town = cells[4].get_text(strip=True)
        collection_post_code = cells[5].get_text(strip=True)
        
        # DELIVERY
        delivery_code = cells[6].get_text(strip=True)
        delivery_town = cells[7].get_text(strip=True)
        delivery_post_code = cells[8].get_text(strip=True)
        
        # DELIVERY DATE (input)
        del_date_el = cells[9].find('input')
        existing_delivery_date = del_date_el.get('value', '').strip() if del_date_el else ''
        
        # CHARGE (input)
        charge_el = cells[10].find('input')
        existing_charge = charge_el.get('value', '').strip() if charge_el else ''
        
        # SERVICE TYPE (select)
        service_el = cells[11].find('select')
        service_type = ''
        service_options = []
        if service_el:
            selected = service_el.find('option', selected=True)
            service_type = selected.get('value', '') if selected else ''
            for opt in service_el.find_all('option'):
                service_options.append({
                    'value': opt.get('value', ''),
                    'label': opt.get_text(strip=True),
                    'selected': opt.has_attr('selected')
                })
        
        # ROUTE ESTIMATE
        route_estimate = cells[12].get_text(strip=True) if len(cells) > 12 else ''
        route_distance_km = None
        route_duration = None
        if route_estimate:
            dist_match = re.search(r'([\d,\.]+)\s*km', route_estimate)
            if dist_match:
                route_distance_km = float(dist_match.group(1).replace(',', '.'))
            dur_match = re.search(r'(\d+h\s*\d*m?)', route_estimate)
            if dur_match:
                route_duration = dur_match.group(1).strip()
        
        # DESIRED COLLECT DATE
        desired_collect_date = cells[13].get_text(strip=True) if len(cells) > 13 else ''
        
        # DESIRED DELIVERY DATE
        desired_delivery_date = cells[14].get_text(strip=True) if len(cells) > 14 else ''
        
        # SPECIAL INSTRUCTIONS
        special_instructions = cells[15].get_text(strip=True) if len(cells) > 15 else ''
        
        # Parse flags utiles
        needs_trailer = bool(re.search(r'needs?\s+trailer', special_instructions, re.IGNORECASE))
        is_driveable = bool(re.search(r'driveable', special_instructions, re.IGNORECASE))
        is_rollable = bool(re.search(r'rollable', special_instructions, re.IGNORECASE))
        
        # Group ref entre parenthèses
        group_ref_match = re.search(r'\(([A-Z0-9]+)\)\s*$', special_instructions)
        group_ref = group_ref_match.group(1) if group_ref_match else ''
        
        vehicle = {
            'tender_vehicle_id': tender_vehicle_id,
            'vehicle_index': idx,
            'make_model': make_model,
            'make': make,
            'model': model,
            'vehicle_type': vehicle_type,
            'fuel_type': fuel_type,
            'collection_code': collection_code,
            'collection_town': collection_town,
            'collection_post_code': collection_post_code,
            'delivery_code': delivery_code,
            'delivery_town': delivery_town,
            'delivery_post_code': delivery_post_code,
            'route_estimate_raw': route_estimate,
            'route_distance_km': route_distance_km,
            'route_duration': route_duration,
            'desired_collect_date': desired_collect_date,
            'desired_delivery_date': desired_delivery_date,
            'existing_charge': existing_charge,
            'existing_delivery_date': existing_delivery_date,
            'service_type': service_type,
            'service_options': service_options,
            'special_instructions': special_instructions,
            'needs_trailer': needs_trailer,
            'is_driveable': is_driveable,
            'is_rollable': is_rollable,
            'group_ref': group_ref,
            'link_move': link_move
        }
        
        print(f"  ✓ [{idx}] {make_model} | {collection_town} → {delivery_town} | {route_distance_km}km")
        return vehicle
        
    except Exception as e:
        print(f"  ❌ Erreur parsing row {idx}: {str(e)}")
        return None


def scrape_intender(country="germany"):
    """Scrape la page InTender pour récupérer les offres ouvertes au bidding."""
    try:
        print(f"🎯 Début du scraping InTender {country.upper()}...")
        
        # Login avec exactement le même flow que le scraper existant
        session, headers = erac_login_for_tender(country)
        
        # Récupérer la page InTender
        print("📊 Récupération de la page InTender...")
        tender_response = session.get(
            'https://erac.hkremarketing.com/Vendor/Tender/InTender',
            headers=headers
        )
        
        print(f"📡 HTTP Status: {tender_response.status_code}")
        print(f"📡 URL finale: {tender_response.url}")
        print(f"📡 Taille HTML: {len(tender_response.text)} caractères")
        
        if tender_response.status_code != 200:
            raise ValueError(f"HTTP {tender_response.status_code} sur InTender")
        
        # Debug: vérifier le contenu de la page
        html_text = tender_response.text
        has_tender_title = 'Offered for Tender' in html_text
        has_login = 'LoginId' in html_text
        has_table = 'tblVehicles' in html_text
        has_closed = 'Closed' in html_text
        
        print(f"📡 Contient 'Offered for Tender': {has_tender_title}")
        print(f"📡 Contient 'LoginId' (page login): {has_login}")
        print(f"📡 Contient 'tblVehicles': {has_table}")
        print(f"📡 Contient 'Closed': {has_closed}")
        
        # Sauvegarder le HTML pour debug
        try:
            with open('/tmp/intender_debug.html', 'w', encoding='utf-8') as f:
                f.write(html_text)
            print("📡 HTML sauvegardé dans /tmp/intender_debug.html")
        except:
            pass
        
        if has_login and not has_tender_title:
            raise ValueError("Session expirée - redirigé vers login. Vérifiez les credentials.")
        
        if not has_table:
            if has_closed:
                return {
                    'country': country.upper(),
                    'status': 'no_active_tender',
                    'vehicles': [],
                    'count': 0,
                    'timestamp': datetime.utcnow().isoformat(),
                    'debug': {
                        'http_status': tender_response.status_code,
                        'final_url': tender_response.url,
                        'html_size': len(html_text),
                        'has_tender_title': has_tender_title,
                        'has_login': has_login,
                        'has_table': has_table
                    }
                }
            else:
                # Retourner un aperçu du HTML pour debug
                return {
                    'country': country.upper(),
                    'status': 'unexpected_page',
                    'vehicles': [],
                    'count': 0,
                    'timestamp': datetime.utcnow().isoformat(),
                    'debug': {
                        'http_status': tender_response.status_code,
                        'final_url': tender_response.url,
                        'html_size': len(html_text),
                        'has_tender_title': has_tender_title,
                        'has_login': has_login,
                        'has_table': has_table,
                        'html_preview': html_text[:2000]
                    }
                }
        
        print("✓ Page InTender récupérée")
        
        # Parser le HTML
        print("🔍 Parsing des véhicules...")
        result = parse_tender_vehicles(html_text)
        
        result['country'] = country.upper()
        result['status'] = 'active'
        result['timestamp'] = datetime.utcnow().isoformat()
        result['source_url'] = 'https://erac.hkremarketing.com/Vendor/Tender/InTender'
        
        print(f"✅ Scraping InTender terminé: {result['count']} véhicules")
        
        return result
        
    except Exception as e:
        print(f"❌ Erreur scraping InTender: {str(e)}")
        raise


# ============================================================
# NOUVEAUX ENDPOINTS - INTENDER
# ============================================================

@app.route('/scrape/germany/tenders')
def scrape_germany_tenders():
    """Scrape les offres ouvertes au bidding pour l'Allemagne"""
    try:
        data = scrape_intender("germany")
        return jsonify({
            'success': True,
            'data': data,
            'message': f"✅ InTender GERMANY: {data['count']} véhicules à bidder"
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'country': 'GERMANY',
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/scrape/france/tenders')
def scrape_france_tenders():
    """Scrape les offres ouvertes au bidding pour la France"""
    try:
        data = scrape_intender("france")
        return jsonify({
            'success': True,
            'data': data,
            'message': f"✅ InTender FRANCE: {data['count']} véhicules à bidder"
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'country': 'FRANCE',
            'timestamp': datetime.utcnow().isoformat()
        }), 500


# ============================================================
# DÉMARRAGE
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5030))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    print(f"🚀 Démarrage de l'API ERAC Scraper v3.0 sur le port {port}")
    print("=" * 50)
    print("Endpoints disponibles:")
    print("  GET  /                       - Informations de l'API")
    print("  GET  /health                 - Status de santé")
    print("  GET  /scrape/france          - Scraping ERAC France (avec VIN)")
    print("  GET  /scrape/germany         - Scraping ERAC Germany (avec VIN)")
    print("  GET  /scrape/germany/tenders - InTender Germany (offres à bidder)")
    print("  GET  /scrape/france/tenders  - InTender France (offres à bidder)")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
