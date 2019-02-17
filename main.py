import argparse
import os
import queue
from queue import Queue
import threading
import time
from typing import Callable, List
import random
import re # natural sort

import mido

# typing aliases
MidiFile = mido.MidiFile
Message = mido.Message

class Track(threading.Thread):
    def __init__(self, outport, trackId : int):
        super().__init__()
        self._msgQueue : Queue[List[Message]] = queue.Queue()
        self._outport = outport
        self._trackId = trackId
        self._callback = None

    def stop(self):
        self._msgQueue.put(None)

    def queueMidi(self, midi: MidiFile):
        msgList = [msg for msg in midi if not msg.is_meta]
        self._msgQueue.put(msgList)

    def setCallback(self, callback):
        self._callback = callback

    def run(self):
        while True:
            msgList = self._msgQueue.get()
            if msgList is None:
                self._outport.reset()
                return
            for msg in msgList:
                time.sleep(msg.time)
                self._outport.send(msg)
            if self._callback:
                self._callback()



class PatternOrchestra(threading.Thread):
    def __init__(self, nbOfTracks : int, patternsPath : str):
        super().__init__()
        self._outports : List[mido.ports.IOPort] = None
        self._patterns : List[MidiFile] = None
        self._tracks : List[Track] = None
        self._tracksPatternNb : List[int] = None
        self._callbackQueue = queue.Queue()

        # load patterns
        filenames = [os.path.join(patternsPath, os.fsdecode(file))
                     for file in os.listdir(patternsPath)]
        sortedFilenames = sorted(filenames, key=natural_sort_key)
        patterns = [mido.MidiFile(filename) for filename in sortedFilenames]
        if not patterns:
            raise ValueError("no midi found")
        self._patterns = patterns

        # open ports and init tracks
        outports = [port for port in mido.get_output_names() if "loopMIDI" in port]
        print(outports)
        maxNbOfTracks = min(nbOfTracks, len(outports))
        neededOutportsNb = nbOfTracks
        if nbOfTracks > maxNbOfTracks:
            print("starting only {0} of the {1} requested tracks because only {2} output midi port(s) is/are available "
                  "({3} needed)".format(maxNbOfTracks, nbOfTracks, len(outports), neededOutportsNb))
        self._outports = [mido.open_output(outports[i]) for i in range(maxNbOfTracks)]
        tracks = [Track(self._outports[trackNb], trackNb) for trackNb in range(maxNbOfTracks)]
        for i,track in enumerate(tracks):
            track.setCallback(lambda trackNb=i: self._callbackQueue.put(trackNb))
        self._tracks = tracks
        self._tracksPatternNb = [None] * len(self._tracks)

    def stop(self):
        self._callbackQueue.put(None)
        for track in self._tracks:
            track.stop()
        for track in self._tracks:
            track.join()
        for port in self._outports:
            port.close()

    def queuePattern(self, patternNb, trackNb):
        self._tracksPatternNb[trackNb] = patternNb
        if patternNb >= len(self._patterns):
            return
        self._tracks[trackNb].queueMidi(self._patterns[patternNb])

    def queueNeighbourPattern(self, stepSize, trackNb):
        patternNb = self._tracksPatternNb[trackNb] + stepSize
        self.queuePattern(patternNb, trackNb)

    def advanceTrack(self, trackNb : int):
        chance = random.random()
        step = chance < .1
        if step:
            print("{0}: {1} > {2}".format(trackNb, self._tracksPatternNb[trackNb], self._tracksPatternNb[trackNb]+1))
        self.queueNeighbourPattern(step, trackNb)

    def run(self):
        random.seed()

        for i,_ in enumerate(self._tracks):
            self.queuePattern(0, i)

        for track in self._tracks:
            track.start()

        while True:
            trackToAdvance = self._callbackQueue.get()
            if trackToAdvance is None:
                return
            self.advanceTrack(trackToAdvance)




# https://stackoverflow.com/a/16090640/3154813
def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower()
            for text in _nsre.split(s)]

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("midiPath")
    parser.add_argument("nbOfTracks", type=int)
    args = parser.parse_args()

    orchestra = PatternOrchestra(args.nbOfTracks, args.midiPath)
    orchestra.start()

    key = input("Press Enter to quit")
    print("stopping...")

    orchestra.stop()
    orchestra.join()
