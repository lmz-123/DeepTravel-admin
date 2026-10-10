import copy
import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from city_maps import CityMapWorker, enqueue, resolve_city, validate_geometry
from models import Base, City, CityMap
from object_storage import InMemoryObjectStorage


def geometry(code="330100"):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "上城区",
                    "center": [120.2, 30.2],
                    "parent": {"adcode": int(code)},
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[120, 30], [120.4, 30], [120.4, 30.4], [120, 30]]],
                },
            }
        ],
    }


class CityMapTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        self.storage = InMemoryObjectStorage()
        with self.sessions() as db:
            db.add(
                City(
                    id="hz",
                    slug="hangzhou",
                    name="杭州",
                    subtitle="城市",
                    hero_image="x",
                    latitude=30,
                    longitude=120,
                )
            )
            db.commit()
        self.worker = CityMapWorker(
            self.sessions, self.storage, lambda code: geometry(code)
        )

    def tearDown(self):
        self.engine.dispose()

    def test_new_and_imported_cities_are_discovered_and_saved_immutably(self):
        self.worker.reconcile()
        self.assertTrue(self.worker.run_one())
        with self.sessions() as db:
            row = db.get(CityMap, "hz")
            self.assertEqual(row.status, "ready")
            self.assertEqual(row.adcode, "330100")
            self.assertTrue(self.storage.exists(row.object_key))
            self.assertIn(row.version, row.object_key)
            enqueue(db, db.get(City, "hz"), force=True)
            db.commit()
        self.worker.run_one()
        self.assertEqual(len(self.storage.objects), 1)
        self.assertFalse(self.worker.run_one())

    def test_unknown_city_is_not_guessed(self):
        self.assertIsNone(resolve_city("西湖"))
        self.assertEqual(resolve_city("杭州市")["adcode"], "330100")
        self.assertEqual(resolve_city("上海")["adcode"], "310000")
        with self.sessions() as db:
            city = db.get(City, "hz")
            city.name = "不存在的城市"
            row = enqueue(db, city)
            db.commit()
            self.assertEqual(row.status, "needs_city")
        self.assertFalse(self.worker.run_one())

    def test_failure_retries_after_restart_and_keeps_last_good_map(self):
        self.worker.reconcile()
        self.worker.run_one()
        with self.sessions() as db:
            original = db.get(CityMap, "hz").object_key
            enqueue(db, db.get(City, "hz"), force=True)
            db.commit()

        def broken(_):
            raise RuntimeError("private credential must not leak")

        CityMapWorker(self.sessions, self.storage, broken).run_one()
        with self.sessions() as db:
            row = db.get(CityMap, "hz")
            self.assertEqual(row.status, "failed")
            self.assertEqual(row.object_key, original)
            self.assertNotIn("credential", row.error)
            self.assertGreater(row.next_attempt_at, datetime.utcnow())
            row.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.worker.run_one()
        with self.sessions() as db:
            self.assertEqual(db.get(CityMap, "hz").status, "ready")

    def test_abandoned_lease_is_recovered_and_old_city_result_cannot_win(self):
        self.worker.reconcile()
        with self.sessions() as db:
            row = db.get(CityMap, "hz")
            row.status = "processing"
            row.lease_token = "abandoned"
            row.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()

        def change_city(code):
            with self.sessions() as db:
                enqueue(db, db.get(City, "hz"), "440100", force=True)
                db.commit()
            return geometry(code)

        CityMapWorker(self.sessions, self.storage, change_city).run_one()
        with self.sessions() as db:
            row = db.get(CityMap, "hz")
            self.assertEqual(row.adcode, "440100")
            self.assertEqual(row.status, "pending")
            self.assertIsNone(row.object_key)
        self.worker.run_one()
        with self.sessions() as db:
            self.assertEqual(db.get(CityMap, "hz").status, "ready")

    def test_rejects_wrong_city_and_invalid_geometry(self):
        with self.assertRaises(ValueError):
            validate_geometry(geometry(), "440100")
        for point in ([float("nan"), 30], [200, 30], [120, 95]):
            invalid = copy.deepcopy(geometry())
            invalid["features"][0]["properties"]["center"] = point
            with self.assertRaises(ValueError):
                validate_geometry(invalid, "330100")
        invalid = geometry()
        invalid["features"][0]["geometry"]["coordinates"][0].pop()
        with self.assertRaises(ValueError):
            validate_geometry(invalid, "330100")
