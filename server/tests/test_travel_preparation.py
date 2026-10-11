from datetime import date, timedelta
import unittest
from pydantic import ValidationError
from travel_preparation import TravelPreparationInput
from schemas import RouteInput
from multi_city_import import _values


class TravelPreparationTests(unittest.TestCase):
    def ticket(self):
        return dict(enabled=True, admission='ticket', channel_name='景区官方', purchase_url='https://official.example/tickets', source_url='https://official.example', verified_on=date.today().isoformat())

    def test_public_link_validation_and_unknown_fields(self):
        for url in ['http://official.example', 'javascript:alert(1)', 'file:///tmp/a', 'https://user:password@example.com', 'https://127.0.0.1', 'https://foo.local', 'https://example.com:5000', 'https://example.com\\@evil.com']:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                TravelPreparationInput.model_validate({**self.ticket(), 'purchase_url': url})
        with self.assertRaises(ValidationError):
            TravelPreparationInput.model_validate({**self.ticket(), 'price': 99})

    def test_official_channel_requires_review_and_can_be_disabled(self):
        for field in ['channel_name', 'source_url', 'verified_on']:
            value = {**self.ticket(), field: None if field == 'verified_on' else ''}
            with self.assertRaises(ValidationError):
                TravelPreparationInput.model_validate(value)
            TravelPreparationInput.model_validate({**value, 'enabled': False})
        with self.assertRaises(ValidationError):
            TravelPreparationInput.model_validate({**self.ticket(), 'verified_on': date.today()+timedelta(days=1)})
        TravelPreparationInput(enabled=True, admission='free', transport='公共交通')
        TravelPreparationInput(enabled=True, admission='ticket', notices='入口待核实')

    def test_import_preserves_config_and_json_dates(self):
        route = dict(id='route', city_id='city', slug='park', title='公园', subtitle='公园', description='公园', duration_minutes=60, distance_km=1, difficulty='轻松', theme='公园', hero_image='x', travel_preparation={**self.ticket(), 'extra_items':[{'title':'停车','body':'南门','url':''}]})
        values = _values('routes', route)
        self.assertEqual(values['travel_preparation']['verified_on'], date.today().isoformat())
        self.assertEqual(values['travel_preparation']['extra_items'][0]['body'], '南门')
        self.assertEqual(values['content_status'], 'draft')
        self.assertNotIn('travel_preparation', RouteInput.model_validate({k:v for k,v in route.items() if k!='travel_preparation'}).model_fields_set)

class TravelPreparationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        import tempfile
        from unittest.mock import patch
        cls.temp = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {'TESTING': 'true', 'DATABASE_URL': f'sqlite:///{cls.temp.name}/cms.db', 'ADMIN_TOKEN': 'local-config-test', 'NARRATION_PROVIDER': 'fake'}):
            import main
        cls.main = main
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from models import Base
        cls.engine = create_engine(f'sqlite:///{cls.temp.name}/cms.db', connect_args={'check_same_thread': False})
        cls.patches = [patch.object(main, 'engine', cls.engine), patch.object(main, 'SessionLocal', sessionmaker(cls.engine, expire_on_commit=False)), patch.object(main.settings, 'admin_token', 'local-config-test')]
        for item in cls.patches:
            item.start()
        Base.metadata.create_all(cls.engine)
        from fastapi.testclient import TestClient
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.engine.dispose()
        for item in reversed(cls.patches):
            item.stop()
        cls.temp.cleanup()

    def test_admin_saves_all_fields_and_regular_edit_preserves_them(self):
        from models import City, Route
        from datetime import datetime, UTC
        with self.main.SessionLocal() as db:
            db.add(City(id='travel-city', slug='travel-city', name='珠海', subtitle='海边', hero_image='x', latitude=22, longitude=113))
            db.add(Route(id='travel-route', city_id='travel-city', slug='travel-route', title='公园', subtitle='公园', description='内容', duration_minutes=60, distance_km=1, difficulty='轻松', theme='公园', hero_image='x', content_status='published', published_at=datetime.now(UTC)))
            db.commit()
        headers={'Authorization': 'Bearer local-config-test'}
        endpoint='/api/admin/routes/travel-route/travel-preparation'
        self.assertEqual(self.client.put(endpoint,json={}).status_code,401)
        data={**TravelPreparationTests().ticket(), 'opening_hours':'09:00—18:00', 'transport':'停车场', 'notices':'带证件', 'extra_items':[{'title':'班车','body':'南门','url':'https://official.example/bus'}]}
        response=self.client.put(endpoint,json=data,headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['travel_preparation']['extra_items'][0]['body'],'南门')
        route=response.json()
        route.pop('travel_preparation')
        response=self.client.put('/api/admin/routes/travel-route',json=route,headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['travel_preparation']['opening_hours'],'09:00—18:00')
        self.assertEqual(response.json()['content_status'],'published')
        response=self.client.put(endpoint,json={**data,'purchase_url':'javascript:alert(1)'},headers=headers)
        self.assertEqual(response.status_code,422)
        with self.main.SessionLocal() as db:
            self.assertEqual(db.get(Route,'travel-route').travel_preparation['purchase_url'],data['purchase_url'])
        response=self.client.put(endpoint,json={'enabled':False},headers=headers)
        self.assertFalse(response.json()['travel_preparation']['enabled'])
