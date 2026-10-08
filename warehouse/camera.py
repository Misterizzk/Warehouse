"""Single-camera capture off the UI thread. Only the UI thread touches SQLite."""
import queue
import sys
import threading
import time
import cv2

DEVICE_LOCK = threading.Lock()


def open_device(index, stop=None, factory=None):
    factory = factory or cv2.VideoCapture
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if sys.platform == 'win32' else [cv2.CAP_ANY]
    for backend in backends:
        if stop is not None and stop.is_set():return None
        cap = None
        try:
            cap = factory(index, backend)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
                cap.set(cv2.CAP_PROP_FPS,15)
                ok, frame = cap.read()
                if ok and frame is not None:return cap, frame
        except Exception:
            pass
        if cap is not None:cap.release()
    return None


def decode_frame(frame, detector=None):
    detector = detector or cv2.QRCodeDetector()
    height,width=frame.shape[:2]
    scale=min(1,1280/max(width,height))
    source=cv2.resize(frame,(round(width*scale),round(height*scale))) if scale<1 else frame
    ok,codes,points,_=detector.detectAndDecodeMulti(source)
    found=[(code,pts/scale) for code,pts in zip(codes,points) if code] if ok and points is not None else []
    if not found:
        code,points,_=detector.detectAndDecode(source)
        if code and points is not None:found=[(code,points.reshape(4,2)/scale)]
    return found


class CameraWorker:
    def __init__(self):
        self.stop_event=threading.Event()
        self.frames=queue.Queue(maxsize=1)
        self.messages=queue.Queue()
        self.thread=None

    def start(self,index=0,discover=False):
        if self.thread is not None and self.thread.is_alive():raise ValueError('Kamera masih berhenti. Tunggu sebentar.')
        if not DEVICE_LOCK.acquire(blocking=False):raise ValueError('Kamera masih digunakan. Tunggu proses sebelumnya berhenti.')
        for mailbox in (self.frames,self.messages):
            try:
                while True:mailbox.get_nowait()
            except queue.Empty:pass
        self.stop_event.clear()
        self.thread=threading.Thread(target=self.run,args=(index,discover),daemon=True)
        self.thread.start()

    def run(self,index,discover):
        cap=None
        try:
            if discover:
                devices=[]
                for number in range(5):
                    if self.stop_event.is_set():break
                    self.messages.put(('info',f'Mencari perangkat {number+1} dari 5…'))
                    opened=open_device(number,self.stop_event)
                    if opened:
                        cap,_=opened
                        devices.append(number)
                        cap.release()
                        cap=None
                self.messages.put(('devices',devices))
                return
            opened=open_device(index,self.stop_event)
            if not opened:
                if not self.stop_event.is_set():raise ValueError('Kamera tidak dapat dibuka. Tutup Camera/Teams/Zoom, periksa izin kamera desktop Windows, lalu coba perangkat lain.')
                return
            cap,frame=opened
            detector=cv2.QRCodeDetector()
            while not self.stop_event.is_set():
                found=decode_frame(frame,detector)
                packet=(frame,found)
                try:self.frames.get_nowait()
                except queue.Empty:pass
                self.frames.put_nowait(packet)
                if self.stop_event.wait(.06):break
                ok,frame=cap.read()
                if not ok or frame is None:raise ValueError('Sambungan kamera terputus. Periksa perangkat, lalu aktifkan kamera kembali.')
        except Exception as exc:
            self.messages.put(('error',str(exc)))
        finally:
            if cap is not None:cap.release()
            self.stop_event.set()
            DEVICE_LOCK.release()
            self.messages.put(('stopped',None))

    def stop(self):
        self.stop_event.set()
