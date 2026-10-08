"""Stable batch QR payloads and printable labels shared by desktop and scanner."""
import base64
import io
import qrcode
from PIL import Image, ImageDraw, ImageFont


def payload(batch_id):
    if not isinstance(batch_id, str) or not batch_id or batch_id != batch_id.strip() or len(batch_id) > 100:
        raise ValueError('ID batch tidak valid.')
    return 'ID:' + batch_id


def resolve(db, value):
    """Exact ID lookup; never infer batch from material or location."""
    if not isinstance(value, str) or not value.startswith('ID:'):
        raise ValueError('QR bukan identitas batch Warehouse Check.')
    key = value[3:]
    if payload(key) != value:
        raise ValueError('Isi QR tidak valid.')
    row = db.execute('SELECT * FROM batches WHERE id=?', (key,)).fetchone()
    if row is None:
        raise ValueError('Batch QR tidak ditemukan di database ini.')
    return dict(row)


def qr_image(batch_id):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(payload(batch_id))
    qr.make(fit=True)
    return qr.make_image(fill_color='black', back_color='white').convert('RGB')


def font(size, bold=False):
    name = 'arialbd.ttf' if bold else 'arial.ttf'
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default(size=size)


def label_image(item):
    image = Image.new('RGB', (1200, 600), 'white')
    draw = ImageDraw.Draw(image)
    qr = qr_image(item['id'])
    # Integer scaling preserves crisp modules and the four-module quiet zone.
    side = qr.width // 10
    qr = qr.resize((side * (500 // side),) * 2, Image.Resampling.NEAREST)
    image.paste(qr, (20 + (500-qr.width)//2, (600-qr.height)//2))
    def line(text, y, size=30, bold=False):
        face = font(size, bold)
        while draw.textlength(text, font=face) > 630 and size > 16:
            size -= 1
            face = font(size, bold)
        if draw.textlength(text, font=face) > 630:
            while draw.textlength(text+'...', font=face) > 630:
                text = text[:-1]
            text += '...'
        draw.text((545, y), text, fill='black', font=face)
    line('WAREHOUSE CHECK | DEMO', 40, 30, True)
    line(item['material'], 110, 42, True)
    line(item['description'], 170, 28)
    line('Lokasi: ' + item['location_code'], 240, 32, True)
    line('GR Date: ' + item['received_date'], 300)
    line('Batch ID', 390, 22)
    line(item['id'], 430, 26, True)
    line('Scan untuk melihat data batch terkini.', 520, 24)
    return image


def print_document(item):
    stream = io.BytesIO()
    label_image(item).save(stream, format='PNG')
    data = base64.b64encode(stream.getvalue()).decode('ascii')
    return '''<!doctype html><html lang="id"><meta charset="utf-8">
<title>Cetak label Warehouse Check</title><style>
body{font:16px Arial;background:#edf1f5;padding:24px;color:#182b40}
img{display:block;width:100mm;height:50mm;background:white;margin:24px 0}
button{padding:12px 24px;cursor:pointer} @page{margin:10mm}
@media print{body{padding:0;margin:0;background:white} .controls{display:none} img{margin:0}}
</style><div class="controls"><h1>Label barang • 100 × 50 mm</h1>
<p>Pilih skala 100% / ukuran aktual. Matikan header dan footer browser.
Untuk kertas label, sesuaikan ukuran kertas pada pengaturan printer.</p>
<button onclick="window.print()">Cetak / cetak ulang label</button></div>
<img alt="Label batch Warehouse Check" src="data:image/png;base64,''' + data + '"></html>'
