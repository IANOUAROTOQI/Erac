# main.py - ERAC Scraper pour Railway avec Supabase

import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime, timezone
import logging
from supabase import create_client, Client
from typing import Dict, List, Any

# Configuration logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('erac_scraper.log')
    ]
)
logger = logging.getLogger(__name__)

class ERACRailwayScaper:
    def __init__(self):
        # Configuration ERAC (reprise de votre code Pipedream)
        self.session = requests.Session()
        
        # Configuration Supabase
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("✅ Supabase client initialized")
        else:
            self.supabase = None
            logger.warning("⚠️ Supabase not configured, will save locally only")
        
        # Headers exactement comme dans votre code Pipedream
        self.headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        }
    
    def scrape_erac_data(self) -> Dict[str, Any]:
        """Votre code Pipedream adapté pour Railway"""
        logger.info("🚀 Début du scraping ERAC")
        
        try:
            # Étape 1: Page de login (votre code exact)
            logger.info("📥 Récupération de la page de login...")
            login_page_response = self.session.get(
                'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', 
                headers=self.headers
            )
            
            login_page_soup = BeautifulSoup(login_page_response.text, 'html.parser')
            token_element = login_page_soup.find('input', {'name': '__RequestVerificationToken'})
            
            if not token_element:
                logger.error("❌ Token non trouvé dans la page de login")
                raise ValueError("Unable to find __RequestVerificationToken on the login page")
            
            token = token_element['value']
            logger.info("🔑 Token extrait avec succès")

            # Étape 2: Login (votre code exact)
            logger.info("🔐 Connexion en cours...")
            login_payload = {
                'LoginId': os.getenv('ERAC_LOGIN_ID', 'ROUYOlivier1'),
                'Password': os.getenv('ERAC_PASSWORD', 'Parkopoly1234'),
                '__RequestVerificationToken': token,
            }
            
            login_headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            login_headers.update(self.headers)
            
            login_response_outbound = self.session.post(
                'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', 
                data=login_payload, 
                headers=login_headers
            )
            
            login_response_inbound = self.session.post(
                'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FInbound', 
                data=login_payload, 
                headers=login_headers
            )
            
            logger.info("✅ Connexion réussie")

            # Étape 3: Conditions d'utilisation (votre code exact)
            logger.info("📋 Gestion des conditions...")
            terms_page_response = self.session.get('https://erac.hkremarketing.com/vendor/scoc', headers=self.headers)
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
            accept_headers.update(self.headers)
            accept_response = self.session.post('https://erac.hkremarketing.com/vendor/scoc', data=accept_payload, headers=accept_headers)
            
            logger.info("✅ Conditions acceptées")

            # Étape 4: Récupération des données (votre code exact)
            logger.info("📊 Récupération des données AJAX...")
            ajax_headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
            }
            ajax_headers.update(self.headers)
            
            # Payload Outbound (votre code exact)
            ajax_payload_Outbound = {
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
            
            # Payload Inbound (votre code exact)
            ajax_payload_inbound = {
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
                'Code': 'inbound',
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
            
            # Exécution des requêtes AJAX (votre code exact)
            ajax_response_inbound = self.session.post(
                'https://erac.hkremarketing.com/Vendor/AjaxSearch', 
                data=ajax_payload_inbound, 
                headers=ajax_headers
            )
            
            ajax_response_outbound = self.session.post(
                'https://erac.hkremarketing.com/Vendor/AjaxSearch', 
                data=ajax_payload_Outbound, 
                headers=ajax_headers
            )

            # Traitement des données (votre code exact)
            data_inbound = ajax_response_inbound.json()
            data_outbound = ajax_response_outbound.json()
            
            combined_data = {
                'inbound': data_inbound['data'],
                'outbound': data_outbound['data'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'total_inbound': len(data_inbound['data']),
                'total_outbound': len(data_outbound['data']),
                'records_total_inbound': data_inbound.get('recordsTotal', 0),
                'records_total_outbound': data_outbound.get('recordsTotal', 0)
            }
            
            logger.info(f"✅ Scraping réussi: {combined_data['total_outbound']} outbound, {combined_data['total_inbound']} inbound")
            return combined_data
            
        except Exception as e:
            logger.error(f"❌ Erreur durant le scraping: {str(e)}")
            raise
    
    def save_to_supabase(self, data: Dict[str, Any]) -> bool:
        """Sauvegarde les données dans Supabase"""
        if not self.supabase:
            logger.warning("⚠️ Supabase non configuré, sauvegarde locale uniquement")
            return False
            
        try:
            logger.info("💾 Sauvegarde vers Supabase...")
            
            # Enregistrement principal
            supabase_record = {
                'id': f"railway_scrape_{int(datetime.now().timestamp())}",
                'scraped_at': data['timestamp'],
                'outbound_data': data['outbound'],
                'inbound_data': data['inbound'],
                'total_outbound': data['total_outbound'],
                'total_inbound': data['total_inbound'],
                'records_total_outbound': data['records_total_outbound'],
                'records_total_inbound': data['records_total_inbound'],
                'status': 'success',
                'source': 'railway',
                'metadata': {
                    'scraper_version': '2.0',
                    'platform': 'railway'
                }
            }
            
            # Insert dans Supabase
            result = self.supabase.table('erac_data').upsert(supabase_record).execute()
            
            if result.data:
                logger.info(f"✅ Données sauvegardées dans Supabase: {len(result.data)} enregistrement(s)")
                return True
            else:
                logger.error("❌ Échec sauvegarde Supabase")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde Supabase: {str(e)}")
            return False
    
    def save_locally(self, data: Dict[str, Any]):
        """Sauvegarde locale de secours"""
        try:
            filename = f"erac_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Sauvegarde locale: {filename}")
            
            # Garder aussi la dernière version
            with open('erac_latest.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde locale: {str(e)}")

def main():
    """Fonction principale"""
    start_time = datetime.now()
    
    try:
        logger.info("🚀 Démarrage du scraper ERAC Railway → Supabase")
        
        scraper = ERACRailwayScaper()
        
        # Scraping des données
        data = scraper.scrape_erac_data()
        
        # Sauvegarde Supabase
        supabase_success = scraper.save_to_supabase(data)
        
        # Sauvegarde locale
        scraper.save_locally(data)
        
        # Résumé
        duration = (datetime.now() - start_time).total_seconds()
        
        print("\n" + "="*60)
        print(f"📊 RÉSUMÉ DU SCRAPING RAILWAY")
        print("="*60)
        print(f"✅ Outbound: {data['total_outbound']} enregistrements")
        print(f"✅ Inbound: {data['total_inbound']} enregistrements")
        print(f"📊 Total ERAC Outbound: {data['records_total_outbound']}")
        print(f"📊 Total ERAC Inbound: {data['records_total_inbound']}")
        print(f"⏱️ Durée: {duration:.1f}s")
        print(f"💾 Supabase: {'✅ Réussi' if supabase_success else '❌ Échec'}")
        print(f"📁 Sauvegarde locale: ✅ Réussie")
        print(f"📅 Timestamp: {data['timestamp']}")
        print("="*60)
        
        return data
        
    except Exception as e:
        logger.error(f"💥 Erreur fatale: {str(e)}")
        print(f"\n❌ ÉCHEC DU SCRAPING: {str(e)}")
        return None

if __name__ == "__main__":
    main()
