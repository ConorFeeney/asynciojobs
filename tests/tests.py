#!/usr/bin/env python3

"""
A simple tool to define ad-hoc 'jobs'
"""

import time
import math
import asyncio
import unittest

from asynciojobs import AbstractJob, PrintJob
from asynciojobs import Job as J
from asynciojobs import Sequence as Seq
from asynciojobs import Scheduler


##############################
def ts():
    """
    a time stamp with millisecond
    """
    # apparently this is not supported by strftime ?!?
    cl = time.time()
    ms = int(1000 * (cl - math.floor(cl)))
    return time.strftime("%M-%S-") + "{:03d}".format(ms)

##############################
async def _sl(n, middle, emergency):
    """
_sl(timeout, middle=False) returns a future that specifies an job like this:
* print incoming `->`
* wait for the time out
* print outgoing `<-`
* return the timeout

_sl(timeout, middle=True) returns a future that specifies an job like this:
* print incoming `->`
* wait for half the time out
* print inside `==` - and optionnally raise an exception there
  if `emergency` is set
* wait for the second half of the time out
* print outgoing `<-`
* return the timeout

"""
    print("{} -> sl({})".format(ts(), n))
    if middle:
        await asyncio.sleep(n / 2)
        print("{} == sl({})".format(ts(), n))
        if emergency:
            raise Exception("emergency exit")
        await asyncio.sleep(n / 2)
    else:
        await asyncio.sleep(n)
    print("{} <- sl({})".format(ts(), n))
    return n


def sl(n): return _sl(n, middle=False, emergency=False)


def slm(n): return _sl(n, middle=True, emergency=False)

##############################


class SleepJob(AbstractJob):

    def __init__(self, timeout, middle=False):
        AbstractJob.__init__(self, forever=False,
                             label="sleep for {}s".format(timeout))
        self.timeout = timeout
        self.middle = middle

    async def co_run(self):
        result = await _sl(self.timeout, middle=self.middle, emergency=False)
        return result

    async def co_shutdown(self):
        pass


class TickJob(AbstractJob):

    def __init__(self, cycle):
        AbstractJob.__init__(self, forever=True,
                             label="Cyclic tick every {}s".format(cycle))
        self.cycle = cycle

    async def co_run(self):
        counter = 1
        while True:
            print("{} -- Tick {} from {}".format(ts(), counter, self.label))
            counter += 1
            await asyncio.sleep(self.cycle)

    async def co_shutdown(self):
        pass


async def co_exception(n):
    await asyncio.sleep(n)
    raise ValueError(10**6 * n)

####################
# shortcuts
SLJ = SleepJob
TJ = TickJob

sep = 40 * '*' + ' '


def check_required_types(scheduler, message):
    wrong = [j for j in scheduler.jobs if not isinstance(
        j, AbstractJob) or not hasattr(j, 'required')]
    if len(wrong) != 0:
        print("Scheduler {} has {}/{} ill-typed jobs"
              .format(len(len(wrong), scheduler.jobs)))
        return False
    return True


def list_sep(scheduler, sep):
    print(sep)
    scheduler.list()
    print(sep)


class Tests(unittest.TestCase):

    ####################
    def test_cycle(self):
        """a simple loop with 3 jobs - cannot handle that"""
        a1, a2, a3 = J(sl(1.1)), J(sl(1.2)), J(sl(1.3))
        a1.requires(a2)
        a2.requires(a3)
        a3.requires(a1)

        sched = Scheduler(a1, a2, a3)

        # these lines seem to trigger a nasty message about a coro not being
        # waited
        self.assertFalse(sched.rain_check())

    ####################
    # Job(asyncio.sleep(0.4))
    # or
    # SleepJob(0.4)
    # are almost equivalent forms to do the same thing
    def test_simple(self):
        """a simple topology, that should work"""
        jobs = SLJ(0.1), SLJ(0.2), SLJ(0.3), SLJ(
            0.4), SLJ(0.5), J(sl(0.6)), J(sl(0.7))
        a1, a2, a3, a4, a5, a6, a7 = jobs
        a4.requires(a1, a2, a3)
        a5.requires(a4)
        a6.requires(a4)
        a7.requires(a5)
        a7.requires(a6)

        sched = Scheduler(*jobs)
        list_sep(sched, sep + "LIST BEFORE")
        self.assertTrue(sched.rain_check())
        self.assertTrue(sched.orchestrate(loop=asyncio.get_event_loop()))
        for j in jobs:
            self.assertFalse(j.raised_exception())
        list_sep(sched, sep + "LIST AFTER")
        print(sep + "DEBRIEF")
        sched.debrief()

    ####################
    def test_forever(self):
        a1, a2, t1 = SLJ(1), SLJ(1.5), TJ(.6)
        a2.requires(a1)
        sched = Scheduler(a1, a2, t1)
        sched.list()
        self.assertTrue(sched.orchestrate())
        sched.list()

    ####################
    def test_timeout(self):
        a1, a2, a3 = [SLJ(x) for x in (0.5, 0.6, 0.7)]
        a2.requires(a1)
        a3.requires(a2)
        sched = Scheduler(a1, a2, a3)
        # should timeout in the middle of stage 2
        self.assertFalse(sched.orchestrate(timeout=1))
        sched.list()

    ####################
    def _test_exc_non_critical(self, verbose):

        print("verbose = {}".format(verbose))
        a1, a2 = SLJ(1), J(co_exception(0.5), label='non critical boom')
        sched = Scheduler(a1, a2, verbose=verbose)
        self.assertTrue(sched.orchestrate())
        print(sep + 'debrief()')
        sched.debrief()

    def test_exc_non_critical_f(
        self): return self._test_exc_non_critical(False)

    def test_exc_non_critical_t(self): return self._test_exc_non_critical(True)

    ####################
    def _test_exc_critical(self, verbose):

        print("verbose = {}".format(verbose))
        a1, a2 = SLJ(1), J(co_exception(0.5),
                           label='critical boom', critical=True)
        sched = Scheduler(a1, a2, verbose=verbose)
        self.assertFalse(sched.orchestrate())
        print(sep + 'debrief()')
        sched.debrief()

    def test_exc_critical_f(self): return self._test_exc_critical(False)

    def test_exc_critical_t(self): return self._test_exc_critical(True)

    ####################
    def test_sequence1(self):
        "a simple sequence"
        a1 = J(sl(0.1), label=1)
        a2 = J(sl(0.1), label=2)
        a3 = J(sl(0.1), label=3)
        s = Seq(a1, a2, a3)
        sched = Scheduler(s)
        list_sep(sched, sep + "sequence1")
        self.assertEqual(len(a1.required), 0)
        self.assertEqual(len(a2.required), 1)
        self.assertEqual(len(a3.required), 1)
        self.assertTrue(check_required_types(sched, "test_sequence1"))
        self.assertTrue(sched.orchestrate())

    ####################
    def test_sequence2(self):
        "a job and a sequence"
        a1 = J(sl(0.1), label=1)
        a2 = J(sl(0.1), label=2)
        a3 = J(sl(0.1), label=3)
        s = Seq(a2, a3, required=a1)
        sched = Scheduler(a1, s)
        list_sep(sched, sep + "sequence2")
        self.assertEqual(len(a1.required), 0)
        self.assertEqual(len(a2.required), 1)
        self.assertEqual(len(a3.required), 1)
        self.assertTrue(check_required_types(sched, "test_sequence2"))
        self.assertTrue(sched.orchestrate())

    ####################
    def test_sequence3(self):
        "a sequence and a job"
        a1 = J(sl(0.1), label=1)
        a2 = J(sl(0.1), label=2)
        s = Seq(a1, a2)
        a3 = J(sl(0.1), label=3, required=s)
        sched = Scheduler()
        sched.update((s, a3))
        list_sep(sched, sep + "sequence3")
        self.assertEqual(len(a1.required), 0)
        self.assertEqual(len(a2.required), 1)
        self.assertEqual(len(a3.required), 1)
        self.assertTrue(check_required_types(sched, "test_sequence3"))
        self.assertTrue(sched.orchestrate())

    ####################
    def test_sequence4(self):
        "a sequence of 2 sequences"
        a1 = J(sl(0.1), label=1)
        a2 = J(sl(0.1), label=2)
        a3 = J(sl(0.1), label=3)
        a4 = J(sl(0.1), label=4)
        s1 = Seq(a1, a2)
        s2 = Seq(a3, a4)
        sched = Scheduler(Seq(s1, s2))
        list_sep(sched, sep + "sequence4")
        self.assertEqual(len(a1.required), 0)
        self.assertEqual(len(a2.required), 1)
        self.assertEqual(len(a3.required), 1)
        self.assertEqual(len(a4.required), 1)
        self.assertTrue(check_required_types(sched, "test_sequence4"))
        self.assertTrue(sched.orchestrate())

    ####################
    def test_sequence5(self):
        "sequences with required"
        a1 = J(sl(0.1), label=1)
        a2 = J(sl(0.1), label=2)
        a3 = J(sl(0.1), label=3)
        a4 = J(sl(0.1), label=4)
        a5 = J(sl(0.1), label=5)
        a6 = J(sl(0.1), label=6)
        s1 = Seq(a1, a2)
        s2 = Seq(a3, a4, required=s1)
        s3 = Seq(a5, a6, required=s2)
        sched = Scheduler(s1, s2, s3)
        list_sep(sched, sep + "sequence5")
        self.assertEqual(len(a1.required), 0)
        self.assertEqual(len(a2.required), 1)
        self.assertEqual(len(a3.required), 1)
        self.assertEqual(len(a4.required), 1)
        self.assertEqual(len(a5.required), 1)
        self.assertEqual(len(a6.required), 1)
        self.assertTrue(check_required_types(sched, "test_sequence5"))
        self.assertTrue(sched.orchestrate())

    ##########
    def test_sequence6(self):
        "adding a sequence"
        sched = Scheduler()
        a1 = J(sl(0.1), label=1)
        a2 = J(sl(0.1), label=2)
        a3 = J(sl(0.1), label=3)
        sched.add(Seq(a1, a2, a3))
        self.assertTrue(sched.orchestrate())

    ##########
    def test_requires_job(self):

        a1 = J(sl(0.1), label="a1")
        a2 = J(sl(0.1), label="a2")
        a3 = J(sl(0.1), label="a3")
        a4 = J(sl(0.1), label="a4")
        a5 = J(sl(0.1), label="a5")

        # several forms to create
        b = J(sl(0.2), required=None)
        self.assertEqual(len(b.required), 0)
        b = J(sl(0.2), required=(None,))
        self.assertEqual(len(b.required), 0)
        b = J(sl(0.2), required=[None])
        self.assertEqual(len(b.required), 0)
        b = J(sl(0.2), required=a1)
        self.assertEqual(len(b.required), 1)
        b = J(sl(0.2), required=(a1,))
        self.assertEqual(len(b.required), 1)
        b = J(sl(0.2), required=[a1])
        self.assertEqual(len(b.required), 1)
        b = J(sl(0.2), label='BROKEN', required=(a1, a2))
        self.assertEqual(len(b.required), 2)
        b = J(sl(0.2), required=[a1, a2])
        self.assertEqual(len(b.required), 2)
        b = J(sl(0.2), required=[a1, (a2,), set([a3, a4]), [[[[[[a5]]]]]]])
        self.assertEqual(len(b.required), 5)

    ##########
    def test_requires_sequence(self):

        # we leave these untouched (no req. added)
        a1 = J(sl(0.1), label="a1")
        a2 = J(sl(0.1), label="a2")
        a3 = J(sl(0.1), label="a3")
        a4 = J(sl(0.1), label="a4")
        a5 = J(sl(0.1), label="a5")

        # re-create these each time to have fresh data
        def bs():
            b1 = J(sl(0.1), label="b1")
            b2 = J(sl(0.1), label="b2")
            b3 = J(sl(0.1), label="b3")
            return b1, b2, b3

        b1, b2, b3, *_ = bs()
        s1 = Seq(b1, b2, b3, required=[a1, a2])
        self.assertEqual(len(b1.required), 2)
        self.assertEqual(len(b2.required), 1)

        b1, b2, b3, *_ = bs()
        s1 = Seq(b1, b2, b3)
        s1.requires([a1, a2])
        self.assertEqual(len(b1.required), 2)
        self.assertEqual(len(b2.required), 1)

    ##########
    def test_timeout(self):
        a1 = J(sl(1), label="a1")
        a2 = J(sl(2), label="a2")
        a3 = J(sl(10), label="a3")
        result = Scheduler(a1, a2, a3).orchestrate(timeout=3)
        self.assertEqual(result, False)
        self.assertEqual(a1.is_done(), True)
        self.assertEqual(a1.result(), 1)
        self.assertEqual(a2.is_done(), True)
        self.assertEqual(a2.result(), 2)
        self.assertEqual(a3.is_done(), False)

    ##########
    def test_forever(self):
        async def tick(n):
            while True:
                print('tick {}'.format(n))
                await asyncio.sleep(n)

        a1 = J(sl(0.5), label="finite")
        a2 = J(tick(0.1), forever=True, label="forever")
        sched = Scheduler(a1, a2)
        result = sched.orchestrate()
        self.assertEqual(result, True)
        self.assertEqual(a1.is_done(), True)
        self.assertEqual(a2.is_done(), False)

    ##########
    def test_creation_scheduler(self):
        sched = Scheduler()
        s = Seq(J(sl(1)), J(sl(2)), scheduler=sched)
        j = J(sl(3), required=s, scheduler=sched)
        # make sure that jobs appended in the sequence
        # even later on are also added to the scheduler
        s.append(J(sl(.5)))
        self.assertEqual(len(sched.jobs), 4)
        self.assertTrue(sched.rain_check())
        self.assertTrue(sched.orchestrate())

    def test_loop(self):
        s = Scheduler()
        Seq(J(sl(.1)), J(sl(.2)),
            scheduler=s)
        loop = asyncio.get_event_loop()
        self.assertTrue(s.orchestrate(loop=loop))

    # if window is defined, total should be a multiple of window
    def _test_window(self, total, window):
        atom = .1
        tolerance = 8  # more or less % in terms of overall time
        s = Scheduler()
        jobs = [PrintJob("{}-th {}s job".format(i, atom),
                         sleep=atom, scheduler=s) for i in range(1, total + 1)]
        import time
        beg = time.time()
        ok = s.orchestrate(jobs_window=window)
        ok or s.debrief(details=True)
        end = time.time()
        duration = end - beg

        # estimate global time
        # unwindowed: overall duration is atom
        # otherwise a multiple of it (assuming total = k*window)
        expected = atom if not window else (total / window) * atom
        print('overall expected {} - measured {}'
              .format(expected, duration))

        distortion = duration / expected
        time_ok = 1 - tolerance / 100 <= distortion <= 1 + tolerance / 100
        if not time_ok:
            print("_test_window - window = {} :"
                  "wrong execution time {} - not within {}% of {}"
                  .format(window, end - beg, tolerance, expected))

        self.assertTrue(time_ok)
        self.assertTrue(ok)

    def test_window(self):
        self._test_window(total=15, window=3)

    def test_no_window(self):
        self._test_window(total=15, window=None)

    ##########
    def test_display(self):

        class FakeTask:

            def __init__(self):
                self._result = 0
                self._exception = None

        def annotate_job_with_fake_task(job, state, boom):
            task = FakeTask()
            if state == "done":
                task._state = asyncio.futures._FINISHED
                job._task = task
                job._running = True
            elif state == "running":
                task._state = "NONE"
                job._task = task
                job._running = True
            elif state == "scheduled":
                task._state = "NONE"
                job._task = task
                job._running = False
            else:
                pass

            # here we assume that a job that has raised an exception is
            # necessarily done
            if boom:
                if state in ("idle", "scheduled", "running"):
                    print("incompatible combination boom x idle - ignored")
                    return
                else:
                    job._task._exception = True
            return job

        class J(AbstractJob):
            pass

        sched = Scheduler()
        previous = None
        for state in "idle", "scheduled", "running", "done":
            for boom in True, False:
                for critical in True, False:
                    for forever in True, False:
                        j = J(critical=critical,
                              forever=forever,
                              label="forever={} crit.={} status={} boom={}"
                              .format(forever, critical, state, boom),
                              required=previous
                              )
                        if annotate_job_with_fake_task(j, state, boom):
                            sched.add(j)
                            previous = j
        sched.list()


if __name__ == '__main__':
    import sys
    if '-v' in sys.argv:
        import scheduler
        scheduler.debug = True
        sys.argv.remove('-v')
    unittest.main()
