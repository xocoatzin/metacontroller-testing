# flake8: noqa

from future.utils import iteritems
from builtins import range

from flask import Flask, jsonify, request
import logging
import json
import arrow
import copy

from dotmap import DotMap


log = logging.getLogger(__name__)

app = Flask(__name__)


PHASE_ORDER = {
    'Unknown': 0,
    'Pending': 1,
    'Running': 2,
    'Succeeded': 3,
    'Failed': 4,
}


@app.route('/syncSequence', methods=['POST'])
def sync_sequence():

    content = DotMap(request.get_json(silent=True))

    parent = content.parent
    children = content.children

    log.info('Received new sync from: {}'.format(parent.metadata.name))

    out_status = copy.deepcopy(parent.status)
    out_children = []

    phase = parent.status.phase or 'Unknown'
    log.info('Parent phase is: {}'.format(phase))

    if phase not in ['Failed', 'Succeeded']:

        # Initialize status
        #  This should run only the first time when the parent status is unset
        if not out_status:
            log.info('Initializing status')
            out_status.phase = 'Pending'

            for_type = parent.spec.forEach.type or "scalar"
            if for_type == "scalar":
                for_value = parent.spec.forEach.scalarValue or 1
                for i in range(for_value):
                    name = "{}-{:0>3}".format(parent.metadata.name, i)
                    out_status.children[name].iterKey = i
                    out_status.children[name].phase = 'Pending'
                    out_status.children[name].activeChild = False
                    out_status.children[name].deletedChild = False
                    out_status.children[name].lastTransition = str(arrow.get())
        # END Initialize status

        # Update status from children
        log.debug('Updating children status')
        pods = children.get('Pod.v1', {})

        for name, body in iteritems(pods):
            phase = body.status.phase or 'Unknown'

            if out_status.children[name]:
                if out_status.children[name].phase != phase:
                    n1 = PHASE_ORDER[phase]
                    n2 = PHASE_ORDER[out_status.children[name].phase]
                    if n1 > n2:
                        log.debug('  - Task "{}" transition: {} -> {}'.format(
                            name, out_status.children[name].phase, phase
                        ))
                        out_status.children[name].phase = phase
                        out_status.children[name].lastTransition = str(
                            arrow.get())
                    else:
                        log.warn(('  - Task "{}" transition rejected:'
                                  ' {} -> {}').format(
                            name, out_status.children[name].phase, phase
                        ))
                else:
                    log.debug('  - Task "{}" phase is: {}'.format(name, phase))
            else:
                log.error('Unknown child: {}'.format(name))

        # Slots

        # This block makes a "batch" of 5 active children at the time.
        # It has no effect on the observed behavior
        slots = 5
        for name, child in iteritems(out_status.children):
            if child.phase in ['Failed', 'Succeeded']:
                out_status.children[name].deletedChild = True
            else:
                if slots > 0:
                    out_status.children[name].activeChild = True
                    slots -= 1
        # END Slots

        # Generate children
        for name, child in iteritems(out_status.children):
            if child.activeChild and not child.deletedChild:
                out_children.append({
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {
                        "name": name,
                    },
                    "spec": {
                        "containers": [{
                            "command": ["sh", "-c", "echo {};sleep 5".format(name)],
                            "image": "busybox",
                            "name": "container-name"
                        }],
                        "restartPolicy": "OnFailure"
                    }
                })
        # END Generate children

        # Counter
        phases = [
            child.phase
            for name, child in iteritems(out_status.children)
        ]

        failed = phases.count('Failed')
        success = phases.count('Succeeded')
        active = len(phases) - failed - success

        out_status.active = active
        out_status.failed = failed
        out_status.succeeded = success

        if active == 0:
            out_status.phase = 'Succeeded'
        elif active > 0:
            out_status.phase = 'Running'

        log.info('Tasks: active: {}, succeeded: {}, failed: {}'.format(
            active, success, failed
        ))
        # END counter

    log.info('{} children returned'.format(len(out_children)))
    out = {
        'children': out_children,
        'status': out_status.toDict()
    }

    # xxx
    children_names = [c['metadata']['name'] for c in out_children]
    log.info('======================= DEBUG =======================')
    log.info('Parent')
    log.info('   resourceVersion: {}'.format(parent.metadata.resourceVersion))
    log.info('   children in status:')
    for name, child in iteritems(parent.status.children):
        log.info('       {:<6} | {:<9} + {:<9} -> {:<9} | {:<1}'.format(
            name,
            child.phase,
            children.get('Pod.v1', {}).get(name, DotMap()).status.phase or "<none>",
            out_status.children[name].phase,
            ('x' if name in children_names else ' ')
        ))

    return jsonify(out)


def _build_logger():
    """Create a formatted logger to be used after instantiaion of worker."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)8s - [%(name)s] %(message)s")

    ch_1 = logging.StreamHandler()
    ch_1.setFormatter(formatter)
    ch_1.setLevel(logging.DEBUG)
    root.addHandler(ch_1)

    logging.getLogger().setLevel(logging.DEBUG)


if __name__ == '__main__':
    _build_logger()
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=False)
