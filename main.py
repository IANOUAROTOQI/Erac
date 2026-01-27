# main.py - API Python complète pour scraping ERAC sur Railway
# SÉCURISÉ: Credentials en variables d'environnement
# NOUVEAU: Indicateurs si dates récupérées

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
        "version": "2.1",
        "endpoints": {
            "/": "GET - Informations de l'API",
            "/scrape/france": "GET - Scraping ERAC France (avec VIN)",
            "/scrape/germany": "GET - Scraping ERAC Germany (avec VIN)", 
            "/health": "GET - Status de santé",
            "/debug/movement/{id}": "GET - Debug d'un mouvement spécifique"
        },
        "description": "API pour scraper les données ERAC France et Germany avec détails voiture"
    })

@app.route('/health')
def health():
    """Endpoint de santé"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "ERAC Scraper API"
    })

def get_mission_details(session, movement_id, country="france", headers=None, debug=False):
    """Récupère les détails d'une mission (VIN, infos voiture, dates, etc.)"""
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
                'vin_retrieved': False,
                'make_model': None,
                'registration': None,
                'unit_no': None,
                'collection_date': None,
                'collection_date_retrieved': False,
                'delivery_date': None,
                'delivery_date_retrieved': False,
            }
            
            # === CHERCHER LE VIN ===
            labels = soup.find_all('label', class_='control-label')
            for label in labels:
                if 'VIN' in label.get_text().upper():
                    parent = label.parent
                    vin_element = parent.find('p', class_='form-control-static')
                    if vin_element:
                        movement_data['vin'] = vin_element.get_text().strip()
                        movement_data['vin_retrieved'] = True
                        if debug: print(f"   ✓ VIN trouvé via label: {movement_data['vin']}")
                        break
            
            if not movement_data['vin']:
                all_labels = soup.find_all('label')
                for label in all_labels:
                    label_text = label.get_text().strip().upper()
                    if 'VIN' in label_text:
                        next_elem = label.find_next('p', class_='form-control-static')
                        if next_elem:
                            movement_data['vin'] = next_elem.get_text().strip()
                            movement_data['vin_retrieved'] = True
                            if debug: print(f"   ✓ VIN trouvé via label+next: {movement_data['vin']}")
                            break
            
            if not movement_data['vin']:
                all_form_statics = soup.find_all('p', class_='form-control-static')
                if debug: print(f"   → Total p.form-control-static trouvés: {len(all_form_statics)}")
                for elem in all_form_statics:
                    text = elem.get_text().strip().upper()
                    if len(text) == 17 and text[0] in 'ZWVJLMRSTUX123456789':
                        movement_data['vin'] = text
                        movement_data['vin_retrieved'] = True
                        if debug: print(f"   ✓ VIN trouvé via form-control-static: {text}")
                        break
            
            if not movement_data['vin']:
                vin_element = soup.find('input', {'id': 'Vin'})
                if vin_element:
                    movement_data['vin'] = vin_element.get('value', '').strip()
                    if movement_data['vin']:
                        movement_data['vin_retrieved'] = True
                        if debug: print(f"   ✓ VIN trouvé via id='Vin': {movement_data['vin']}")
            
            if not movement_data['vin']:
                vin_element = soup.find('input', {'name': 'Vin'})
                if vin_element:
                    movement_data['vin'] = vin_element.get('value', '').strip()
                    if movement_data['vin']:
                        movement_data['vin_retrieved'] = True
                        if debug: print(f"   ✓ VIN trouvé via name='Vin': {movement_data['vin']}")
            
            # === CHERCHER COLLECTION DATE ===
            collection_date_element = soup.find('input', {'id': 'CollectionDate'}) or soup.find('input', {'name': 'CollectionDate'})
            if collection_date_element:
                collection_date_value = collection_date_element.get('value', '').strip()
                if collection_date_value:
                    movement_data['collection_date'] = collection_date_value
                    movement_data['collection_date_retrieved'] = True
                    if debug: print(f"   ✓ Collection Date trouvée: {collection_date_value}")
            
            # === CHERCHER DELIVERY DATE ===
            delivery_date_element = soup.find('input', {'id': 'DeliveryDate'}) or soup.find('input', {'name': 'DeliveryDate'})
            if delivery_date_element:
                delivery_date_value = delivery_date_element.get('value', '').strip()
                if delivery_date_value:
                    movement_data['delivery_date'] = delivery_date_value
                    movement_data['delivery_date_retrieved'] = True
                    if debug: print(f"   ✓ Delivery Date trouvée: {delivery_date_value}")
            
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
            
            return movement_data
            
        else:
            print(f"⚠️ HTTP {response.status_code} pour {movement_id}")
            return {'movement_id': movement_id, 'error': f'HTTP {response.status_code}'}
            
    except Exception as e:
        print(f"❌ Erreur parsing {movement_id}: {str(e)}")
        return {'movement_id': movement_id, 'error': str(e)}


def enrich_missions_with_details(session, missions, country="france", headers=None, delay=0.3):
    """Enrichit les missions avec les détails (VIN, dates, etc.)"""
    enriched = []
    total = len(missions)
    
    for idx, mission in enumerate(missions):
        percent = int((idx + 1) / total * 100)
        reg_no = mission.get('RegNo', 'N/A')
        print(f"[{percent}%] {idx+1}/{total} - {reg_no}")
        
        enriched_mission = {**mission}
        movement_id = mission.get('Id')
        
        if movement_id:
            debug = (idx == 0)
            details = get_mission_details(session, movement_id, country, headers, debug=debug)
            
            # Ajouter les champs enrichis
            enriched_mission['vin'] = details.get('vin')
            enriched_mission['vin_retrieved'] = details.get('vin_retrieved', False)
            enriched_mission['collection_date_details'] = details.get('collection_date')
            enriched_mission['collection_date_retrieved'] = details.get('collection_date_retrieved', False)
            enriched_mission['delivery_date_details'] = details.get('delivery_date')
            enriched_mission['delivery_date_retrieved'] = details.get('delivery_date_retrieved', False)
            
            if details.get('vin'):
                print(f"     ✓ VIN: {details.get('vin')}")
            else:
                print(f"     ✗ VIN non trouvé")
            
            if details.get('collection_date_retrieved'):
                print(f"     ✓ Collection Date: {details.get('collection_date')}")
            else:
                print(f"     ✗ Collection Date non trouvée")
            
            if details.get('delivery_date_retrieved'):
                print(f"     ✓ Delivery Date: {details.get('delivery_date')}")
            else:
                print(f"     ✗ Delivery Date non trouvée")
        else:
            enriched_mission['vin'] = None
            enriched_mission['vin_retrieved'] = False
            enriched_mission['collection_date_details'] = None
            enriched_mission['collection_date_retrieved'] = False
            enriched_mission['delivery_date_details'] = None
            enriched_mission['delivery_date_retrieved'] = False
        
        enriched.append(enriched_mission)
        
        if idx < total - 1:
            time.sleep(delay)
    
    print(f"✅ Enrichissement terminé: {total} missions traitées")
    return enriched


def scrape_erac_country(country="france", enrich_details=True):
    """Fonction de scraping avec credentials par pays"""
    try:
        print(f"🚀 Début du scraping ERAC {country.upper()}...")
        
        # ✅ SÉCURISÉ: Credentials depuis les variables d'environnement
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
        
        # Session HTTP
        session = requests.Session()

        # Headers
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
        
        login_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        login_headers.update(headers)
        
        # Double login
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
            accept_payload = {'action': 'agree', '__RequestVerificationToken': token}
        else:
            accept_payload = {'action': 'agree'}

        accept_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
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
        
        # Payload Outbound (simplifié)
        ajax_payload_outbound = {
            'draw': 2,
            'order[0][column]': 0,
            'order[0][dir]': 'asc',
            'start': 0,
            'length': 500,
            'search[value]': '',
            'search[regex]': 'false',
            'Code': 'outbound',
            'MovementType': 'collections',
        }
        
        # Payload Inbound (simplifié)
        ajax_payload_inbound = {
            'draw': 2,
            'order[0][column]': 0,
            'order[0][dir]': 'asc',
            'start': 0,
            'length': 500,
            'search[value]': '',
            'search[regex]': 'false',
            'Code': 'inbound',
            'MovementType': 'collections',
        }
        
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
        
        # Enrichir avec détails voiture
        if enrich_details:
            print(f"🚗 Enrichissement des données {country.upper()} avec VIN et dates...")
            enriched_inbound = enrich_missions_with_details(
                session, 
                data_inbound['data'], 
                country, 
                ajax_headers,
                delay=0.3
            )
            enriched_outbound = enrich_missions_with_details(
                session, 
                data_outbound['data'], 
                country, 
                ajax_headers,
                delay=0.3
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
            'enriched': enrich_details
        }
        
        print(f"✅ Scraping {country.upper()} réussi")
        print(f"   📤 Outbound: {combined_data['total_outbound']} missions")
        print(f"   📥 Inbound: {combined_data['total_inbound']} missions")
        
        return combined_data
        
    except Exception as e:
        print(f"❌ Erreur lors du scraping {country.upper()}: {str(e)}")
        raise

@app.route('/scrape/france')
def scrape_france():
    """Endpoint pour le scraping ERAC France"""
    try:
        data = scrape_erac_country("france", enrich_details=True)
        
        return jsonify({
            'success': True,
            'data': data,
            'message': f"✅ Scraping FRANCE réussi: {data['total_outbound']} outbound, {data['total_inbound']} inbound"
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'country': 'FRANCE',
            'timestamp': datetime.utcnow().isoformat(),
        }), 500

@app.route('/scrape/germany')
def scrape_germany():
    """Endpoint pour le scraping ERAC Germany"""
    try:
        data = scrape_erac_country("germany", enrich_details=True)
        
        return jsonify({
            'success': True,
            'data': data,
            'message': f"✅ Scraping GERMANY réussi: {data['total_outbound']} outbound, {data['total_inbound']} inbound"
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'country': 'GERMANY',
            'timestamp': datetime.utcnow().isoformat(),
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
        
        # Authentification rapide
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
        
        # Récupérer les détails avec debug
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

if __name__ == '__main__':
    # Configuration pour Railway
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    print(f"🚀 Démarrage de l'API ERAC Scraper v2.1 sur le port {port}")
    print("=" * 50)
    print("Endpoints disponibles:")
    print("  GET  /              - Informations de l'API")
    print("  GET  /health        - Status de santé") 
    print("  GET  /scrape/france - Scraping ERAC France")
    print("  GET  /scrape/germany - Scraping ERAC Germany")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
