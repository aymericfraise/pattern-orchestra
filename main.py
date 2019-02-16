import argparse
import os
import queue
from queue import Queue
import threading
import time
from typing import List

import mido

# typing aliases
MidiFile = mido.MidiFile
Message = mido.Message

class Track(threading.Thread):
    def __init__(self, portName : str):
        super().__init__()
        self._msgQueue : Queue[Message] = queue.Queue()
        self._port = portName

    def stop(self):
        self._msgQueue.put(None)

    def addMidi(self, midi: MidiFile):
        for msg in midi.play(): # msg.time is in seconds because midi.play() is used
            self._msgQueue.put(msg)

    def run(self):
        while True:
            msg = self._msgQueue.get()
            if msg is None:
                print("track stopping")
                break
            time.sleep(msg.time)
            print(msg)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("midi_path")
    args = parser.parse_args()

    midiPatterns = []
    for file in os.listdir(args.midi_path):
        filename = os.fsdecode(file)
        midiPatterns.append(mido.MidiFile(os.path.join(args.midi_path, filename)))


    track = Track("")
    track.start()
    track.addMidi(midiPatterns[1])

    key = input("Press Enter to quit")
    track.stop()
