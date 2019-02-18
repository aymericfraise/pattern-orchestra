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

# https://stackoverflow.com/a/16090640/3154813
def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower()
            for text in _nsre.split(s)]

class Track(threading.Thread):
    """
    plays midi files that have been queued and optionnally calls callback functions after having played each file
    """
    def __init__(self, outport : mido.ports.IOPort, channel : int):
        if not 0 <= channel <= 15 :
            errorStr = "channel number should be between 0 and 15 both included ({0} given)".format(channel)
            raise ValueError(errorStr)
        super().__init__()
        self._msgQueue : Queue[List[Message]] = queue.Queue()
        self._outport = outport
        self._channel = channel
        self._callback : Callable = None

    def stop(self):
        self._msgQueue.put(None)

    def queueMidi(self, midi: MidiFile):
        msgList = [msg for msg in midi if not msg.is_meta]
        for msg in msgList:
            msg.channel = self._channel
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
        if nbOfTracks < 1:
            errorMsg = "nbOfTrack argument has to be at least 1 ({0} given)".format(nbOfTracks)
            raise ValueError(errorMsg)

        super().__init__()
        self._outports : List[mido.ports.IOPort] = None
        self._patterns : List[MidiFile] = None
        self._tracks : List[Track] = None
        self._curPatterns : List[int] = None
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
        maxNbOfTracks = min(nbOfTracks, len(outports)*16)
        maxNbOfOutPorts = (maxNbOfTracks-1) // 16 + 1
        neededNbOfOutports = (nbOfTracks-1) // 16 + 1
        if nbOfTracks >= maxNbOfTracks:
            print("starting only {0} of the {1} requested tracks because only {2} output midi port(s) is/are available "
                  "(16 channels per port, so {3} ports needed)".format(maxNbOfTracks, nbOfTracks, len(outports), neededNbOfOutports))
        self._outports = [mido.open_output(outports[i]) for i in range(maxNbOfOutPorts)]
        tracks = [Track(self._outports[trackNb//16], trackNb%16) for trackNb in range(maxNbOfTracks)]
        for i,track in enumerate(tracks):
            track.setCallback(lambda trackNb=i: self._callbackQueue.put([trackNb]))
        self._tracks = tracks
        self._curPatterns = [None]*len(self._tracks)

    def stop(self):
        self._callbackQueue.put(None)
        for track in self._tracks:
            track.stop()
        for track in self._tracks:
            track.join()
        for port in self._outports:
            port.close()

    def queuePatternOnTrack(self, patternNb, trackNb):
        self._curPatterns[trackNb] = patternNb
        if patternNb >= len(self._patterns):
            return
        self._tracks[trackNb].queueMidi(self._patterns[patternNb])

    def queueNeighbourPatternOnTrack(self, stepSize, trackNb):
        patternNb = self._curPatterns[trackNb] + stepSize
        self.queuePatternOnTrack(patternNb, trackNb)

    def repeat(self, trackNb):
        self.queueNeighbourPatternOnTrack(0, trackNb)

    def next(self, trackNb):
        self.queueNeighbourPatternOnTrack(1, trackNb)

    def beforeStart(self):
        self.queuePatternOnTrack(0,0)
        for i in range(1, len(self._tracks)):
            self.queuePatternOnTrack(1, i)

    def advanceTrack(self, trackNb : int):
        if trackNb is 0:
            self.repeat(trackNb)
            return
        stepChance = .1
        if random.random() < stepChance:
            print("{0}: {1} > {2}".format(trackNb, self._curPatterns[trackNb],self._curPatterns[trackNb]+1))
            self.next(trackNb)
        else:
            self.repeat(trackNb)

    def run(self):
        random.seed()

        self.beforeStart()

        for track in self._tracks:
            track.start()

        while True:
            args = self._callbackQueue.get()
            if args is None:
                return
            self.advanceTrack(*args)

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
