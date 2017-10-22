#!/usr/bin/env python
# Copyright Genome Research Ltd 2014
# Author Guy Coates <gmpc@sanger.ac.uk>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
Parallel find implementation
"""

from mpi4py import MPI
from lib.parallelwalk  import ParallelWalk
import argparse
import os
import stat
import sys
import traceback
from lib import readdir

def safestat(filename):
    """lstat sometimes get Interrupted system calls; wrap it up so we can
    retry"""
    while True:
        try:
            statdata = os.lstat(filename)
            return(statdata)
        except IOError as error:
            if error.errno != 4:
                raise

class Results():
    def __init__(self):
        self.entries=0
        self.matches=0

class find(ParallelWalk):

    def check_match(self, filename, stat_t):
      match=True 
      if match is True and args.name is not None:
        if args.name not in os.path.basename(filename):
          match = False
      if match is True and args.size is not None:
        if int(args.size) != stat_t.st_size:
          match = False
      if match is True and args.newer is not None:
        if int(args.newer) >= stat_t.st_mtime:
          match = False
      if match:
        if args.silent is False:
          print (filename)
          print (stat_t)
        return True
      else:
        return False

    """Extend the generic parallel walk class so that is checks a match
    of all the files the crawler encounters.
    """
    def ProcessFile(self, filename):
        stat_t = os.lstat(filename)
        if self.check_match(filename,stat_t) is True:
          self.results.matches += 1
        self.results.entries += 1

class MPIargparse(argparse.ArgumentParser):
    """Subclass argparse so we can add a call to Abort, to tidy up MPI bits and pieces."""
    def error(self,message):
        self.print_usage(sys.stderr)
        Abort()

    def print_help(self, file=None):
        argparse.ArgumentParser.print_help(self, file=None)
        Abort()

def Abort():
    print 
    MPI.COMM_WORLD.Abort(0)
    exit (0)

def parseargs():
    parser = MPIargparse(
        formatter_class = argparse.RawDescriptionHelpFormatter,
        description = "A parallel implemntation of find. Add more text here..", add_help=False,
        epilog="""

This program searches. 

The program should be invoked via mpirun. 
Increase the process count to obtain the required amount of performance. 

"""
)
    parser.add_argument("-h", help="print sizes in human readable format.", action="store_true", 
                        default=False)
    parser.add_argument("-?","--help", action="help", help="print this help message.")
    parser.add_argument("DIR", nargs=1, help="Directory to count.")
    parser.add_argument("-v", help="verbose mode for debugging", action="store_true", default=False)
    parser.add_argument("-name", help="match substring in name", default=None)
    parser.add_argument("-size", help="match file size", default=None)
    parser.add_argument("-newer", help="match newer timestamps", default=None)
    parser.add_argument("-silent", help="silent. Don't output names", action="store_true", default=False)

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    return(args)


def verbose(msg):
  if args.v == True:
    print ("# Rank %d: %s" % (rank, msg))


# Begin main program
try:
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    workers = comm.size

    args = parseargs()
    topdir = args.DIR[0].rstrip("/")

    verbose("Rank checking in.")

    if rank == 0:
        # Enumerate all of the files/dirs in the top level.
        if workers == 1 and args.silent is not True:
            print ("WARNING: Running in non-parallel mode.")
            print ("Did you invoke me via mpirun...?")

        try:
            # I'm seeing some weird bug where funny characters show up in the d_names...
            #entries = [ e.d_name for e in eaddir.readdir(topdir) if not e.d_name in [".", ".."] ]
            entries = os.listdir(topdir)
        except OSError as err:
            print ("OS Error: %s" %err)
            Abort()
        fullpaths = [ os.path.join(topdir,e) for e in entries ]

        total_matches = 0
        total_entries = 0

        verbose(fullpaths)
        for i in fullpaths:
            statdata = os.lstat(i)
            mode = statdata.st_mode
            if  stat.S_ISDIR(mode):
                # Tell peers to start crawlers.
                comm.bcast("Crawl", root=0)
                crawler = find(comm, results=Results())
                results = crawler.Execute(i)
                matches = sum([ r.matches for r in results])
                entries = sum([ r.entries for r in results])
                verbose ("%d/%d in %s" % (matches,entries, i))
                total_matches += matches
                total_entries += entries
            else:
                print ("Not sure what to do about %s" % i)

        comm.bcast("shutdown", root=0)

        print ( "%d/%d" % (total_matches,total_entries))
    else:
        # listen for work
        while True:
            data = comm.bcast("", root=0)
            if data != "shutdown":
                crawler = find(comm, results=Results())
                crawler.Execute(None)
            else:
                exit(0)

except (Exception, KeyboardInterrupt) as err:
    print ("Exception on rank %i" %rank)
    print (err)
    print (traceback.print_tb(sys.exc_info()[2]))
    Abort()
