import base64
import io
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from warehouse.database import connect, seed_demo
from warehouse.inventory import Inventory
from warehouse.labels import payload, resolve, qr_image, label_image, print_document


class LabelTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/'demo.db'
        self.db=connect(self.path)
        seed_demo(self.db)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def decode(self,image):
        return cv2.QRCodeDetector().detectAndDecode(np.array(image))[0]

    def test_existing_and_new_roundtrip(self):
        item=dict(self.db.execute('SELECT * FROM batches WHERE id=?',('DEMO-0001',)).fetchone())
        key=Inventory(self.db).add(item)
        for batch in ('DEMO-0001',key):
            data=resolve(self.db,payload(batch))
            for image in (qr_image(batch),label_image(data)):
                output=Path(self.folder.name)/'label.png'
                image.save(output)
                with Image.open(output) as saved:
                    decoded=self.decode(saved.convert('RGB'))
                self.assertEqual(decoded,payload(batch))
                self.assertEqual(resolve(self.db,decoded)['id'],batch)

    def test_stable_after_edit_restart_and_reprint(self):
        old=payload('DEMO-0001')
        item=resolve(self.db,old)
        Inventory(self.db).update(item['id'],dict(item,description='Changed description',location_code='B-B03-K03-R01-T03'))
        self.db.close()
        self.db=connect(self.path)
        updated=resolve(self.db,old)
        self.assertEqual(updated['description'],'Changed description')
        self.assertEqual(self.decode(label_image(updated)),old)
        html=print_document(updated)
        encoded=html.split('base64,')[1].split('"')[0]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
            self.assertEqual(self.decode(image),old)
        self.assertIn('window.print()',html)

    def test_invalid_unknown_and_exact_matching(self):
        for value in ('','MAT-001','ID:','ID:missing','ID:DEMO-000','ID:DEMO-0001 ',"ID:' OR 1=1 --"):
            with self.subTest(value=value),self.assertRaises(ValueError):
                resolve(self.db,value)


if __name__=='__main__':unittest.main()
