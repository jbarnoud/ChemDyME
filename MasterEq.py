from subprocess import Popen, PIPE
import os

# Class to run master equation calculation
class MasterEq:

    def __init__(self):

        self.newSpeciesFound = False
        self.time = 0.0
        self.ene = 0
        self.prodName = 'none'
        self.visitedList = []
        self.equilCount = 0
        try:
            self.MESCommand = os.environ['CHEMDYME_ME_PATH']
        except:
            self.MESCommand = 'mesmer'

    def runTillReac(self, args2):
        p = Popen([self.MESCommand,args2], stdout=PIPE, stderr=PIPE )
        stdout, stderr = p.communicate()
        out = stderr.decode("utf-8")
        lines = str(out).split('\n')
        words = lines[len(lines)-5].split(' ')
        self.ene = float(words[1])
        words = lines[len(lines)-4].split(' ')
        self.time = float(words[1])
        words = lines[len(lines)-3].split(' ')
        self.prodName = words[1]


    def repeated(self):
        length = len(self.visitedList)
        if length > 2:
            if self.visitedList[(length-1)] == self.visitedList[(length - 3)]:
                return True
        else:
            return False

