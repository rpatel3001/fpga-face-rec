print("started")

from pynq.lib import MicroblazeLibrary
import sqlite3
from multiprocessing import Queue, Process, Value, Array
import ctypes
import cv2
from time import time, sleep
import numpy as np
from pynq.lib.video import VideoMode, PIXEL_BGR
from pynq.overlays.rmarduino import RmArduinoOverlay

print("imported")

VIDEO_OUT = False

base = RmArduinoOverlay("rmarduino.bit", download=True)

print("downloaded")

base.latch_pwr.write(0)

XRES = 1280
YRES = 720
procScale = 4
numFaces = 10

base_dir = '/home/xilinx/capstone'

if VIDEO_OUT:
    Mode = VideoMode(XRES, YRES, 24)
    hdmi_out = base.video.hdmi_out
    hdmi_out.configure(Mode, PIXEL_BGR)
    hdmi_out.start()

    print("hdmi started")

if 'videoIn' in globals():
    videoIn.release()

videoIn = cv2.VideoCapture(0)
if not videoIn.isOpened():
    raise RuntimeError("Failed to open camera.")
videoIn.set(cv2.CAP_PROP_FRAME_WIDTH, XRES)
videoIn.set(cv2.CAP_PROP_FRAME_HEIGHT, YRES)

font = cv2.FONT_HERSHEY_SIMPLEX

print("done")

db = sqlite3.connect(base_dir + '/database.sqlite3')
db.row_factory = sqlite3.Row
cur = db.cursor()

current_location = 1

users = dict([(x['id'], dict(zip(('name', 'access_level'), (x['name'], x['access_level']))))
              for x in cur.execute('''select * from users''').fetchall()])
users[-1] = dict(zip(('name', 'access_level'), ('Unknown', -1)))
locks = dict([(x['id'], dict(zip(('location', 'access_level'), (x['location'], x['access_level']))))
              for x in cur.execute('''select * from locks''').fetchall()])
print(users)
print(locks)


def blink_status(run, cmd_queue):
    try:
        base.status_led.write(0)
        while run.value:
            if cmd_queue.empty():
                base.status_led.write(1)
                sleep(.1)
                base.status_led.write(0)
                sleep(.1)
                base.status_led.write(1)
                sleep(.1)
                base.status_led.write(0)
                sleep(.7)
            else:
                cmd = cmd_queue.get()
                if len(cmd) % 2 == 1:
                    continue
                for on, off in [cmd[i:i+2] for i in range(0, len(cmd), 2)]:
                    base.status_led.write(1)
                    sleep(on)
                    base.status_led.write(0)
                    sleep(off)
    except KeyboardInterrupt:
        run.value = False

    base.status_led.write(0)


def processframes(run, frame_buf, faces_flat, procTime, procCnt, labels, confidences):
    try:
        face_cascade = cv2.CascadeClassifier(
            base_dir + '/lbpcascade_frontalface.xml')
        face_recognizer = cv2.face.LBPHFaceRecognizer_create()
        face_recognizer.read(base_dir + "/recognizer.dat")

        frame = np.frombuffer(frame_buf.get_obj(),
                              dtype=np.uint8).reshape([YRES, XRES, 3])
        while run.value:
            startProc = time()
            gray = cv2.cvtColor(cv2.resize(
                frame, (XRES//procScale, YRES//procScale)), cv2.COLOR_BGR2GRAY)
            faces_raw = face_cascade.detectMultiScale(gray, 1.2, 3)
            faces_flat[:] = [0] * len(faces_flat)
            labels[:] = [-1] * len(labels)
            confidences[:] = [-1] * len(confidences)
            for i, (x, y, w, h) in enumerate(faces_raw[:numFaces]):
                label, confidence = face_recognizer.predict(gray[y:y+w, x:x+h])
                labels[i] = label
                confidences[i] = confidence
                faces_flat[i*4] = x * procScale
                faces_flat[i*4+1] = y * procScale
                faces_flat[i*4+2] = w * procScale
                faces_flat[i*4+3] = h * procScale
            procTime.value += time() - startProc
            procCnt.value += 1
    except KeyboardInterrupt:
        run.value = False


print("started")

frame_buf = Array(ctypes.c_uint8, XRES*YRES*3)
procTime = Value(ctypes.c_double, 0.000001)
procCnt = Value(ctypes.c_int, 0)
run = Value(ctypes.c_bool, True)
faces_flat = Array(ctypes.c_int, 4 * numFaces)
labels = Array(ctypes.c_int, numFaces)
confidences = Array(ctypes.c_double, numFaces)
frame = np.frombuffer(frame_buf.get_obj(),
                      dtype=np.uint8).reshape([YRES, XRES, 3])

procthread = Process(target=processframes, args=(
    run, frame_buf, faces_flat, procTime, procCnt, labels, confidences))
# procthread = Process(target=cProfile.run, args=('processframes(run, frame_buf, faces_flat, procTime, labels, confidences)', None, 'cumtime'))
procthread.start()

status_cmds = Queue()

statusthread = Process(target=blink_status, args=(run, status_cmds))
statusthread.start()

time_latch_off = 0

fpsTime = .000001
fpsCnt = 0
try:
    while not (base.btns_gpio.read() & 0x8):
        fps = str(round(fpsCnt / fpsTime, 1))
        start = time()
        procfps = str(round(procCnt.value / (procTime.value), 1))
        print("fps %s proc %s\r" % (fps, procfps), end="")

        latch_open = base.latch_open.read()

        if not latch_open:
            base.latch_pwr.write(time() <= time_latch_off)
        else:
            base.latch_pwr.write(0);

        if VIDEO_OUT:
            outframe = hdmi_out.newframe()
        else:
            outframe = np.ndarray((YRES, XRES, 3), int)
        ret, newframe = videoIn.read()
        if (not ret):
            raise RuntimeError("Failed to read from camera.")

        np.copyto(frame, newframe)

        outframe[...] = newframe

        faces_parsed = []
        for i in range(0, len(faces_flat), 4):
            faces_parsed.append(
                (faces_flat[i], faces_flat[i+1], faces_flat[i+2], faces_flat[i+3]))

        for label, confidence, (x, y, w, h) in zip(labels, confidences, faces_parsed):
            if x+y+w+h == 0:
                continue
            print("%s %.2f %s" % (users[label]['name'], confidence, users[label]
                                  ['access_level'] >= locks[current_location]['access_level']))
            if users[label]['access_level'] >= locks[current_location]['access_level'] and not latch_open:
                time_latch_off = time() + .5
                status_cmds.put((.5, .5, .5, .5))
            if VIDEO_OUT:
                cv2.rectangle(outframe, (x, y), (x+w, y+h), (255, 0, 0), 2)
                roi_color = outframe[y:y+h, x:x+w]
                cv2.putText(outframe, "%s %.2f" % (
                    users[label], confidence), (x, y), font, 1, (0, 0, 255), 2, cv2.LINE_AA)

        if VIDEO_OUT:
            h = cv2.getTextSize(fps, font, 1, 2)[0][1]
            cv2.putText(outframe, fps, (0, 30), font,
                        1, (0, 0, 255), 2, cv2.LINE_AA)
            cv2.putText(outframe, procfps, (0, 40 + h),
                        font, 1, (0, 0, 255), 2, cv2.LINE_AA)
            hdmi_out.writeframe(outframe)

        end = time()
        fpsTime += end - start
        fpsCnt += 1
        sleep(max(0, 1.0/30 - (end - start)))
except KeyboardInterrupt:
    pass

print("joining")

if VIDEO_OUT:
    outframe.fill(0)
    hdmi_out.writeframe(outframe)

base.latch_pwr.write(0)
run.value = False

procthread.join()
statusthread.join()

print("FPS: %.2f, PROC: %.2f" %
      (fpsCnt / fpsTime, procCnt.value / procTime.value))

print("closing db")
db.close()

print("closing vid in")
videoIn.release()

if VIDEO_OUT:
    print("closing hdmi")
    hdmi_out.stop()
    hdmi_out.close()
