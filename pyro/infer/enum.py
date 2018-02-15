from __future__ import absolute_import, division, print_function

import math

import torch
from torch.autograd import Variable

from pyro import poutine
from pyro.poutine.trace import Trace
from six.moves.queue import LifoQueue


def _iter_discrete_filter(name, msg):
    return ((msg["type"] == "sample") and
            (not msg["is_observed"]) and
            getattr(msg["fn"], "enumerable", False) and
            (msg["infer"].get("enumerate", "sequential") == "sequential"))


def _iter_discrete_escape(trace, msg):
    return _iter_discrete_filter(msg["name"], msg) and (msg["name"] not in trace)


def iter_discrete_traces(graph_type, fn, *args, **kwargs):
    """
    Iterate over all discrete choices of a stochastic function.

    When sampling continuous random variables, this behaves like `fn`.
    When sampling discrete random variables, this iterates over all choices.

    This yields `(scale, trace)` pairs, where `scale` is the probability of the
    discrete choices made in the `trace`.

    :param str graph_type: The type of the graph, e.g. "flat" or "dense".
    :param callable fn: A stochastic function.
    :returns: An iterator over (scale, trace) pairs.
    """
    queue = LifoQueue()
    queue.put(Trace())
    q_fn = poutine.queue(fn, queue=queue)
    while not queue.empty():
        q_fn = poutine.queue(fn, queue=queue, escape_fn=_iter_discrete_escape)
        full_trace = poutine.trace(q_fn, graph_type=graph_type).get_trace(*args, **kwargs)

        # Scale trace by probability of discrete choices.
        log_pdf = full_trace.batch_log_pdf(site_filter=_iter_discrete_filter)
        if isinstance(log_pdf, Variable):
            scale = torch.exp(log_pdf.detach())
        else:
            scale = math.exp(log_pdf)
        yield scale, full_trace
