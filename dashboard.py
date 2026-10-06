"""Dashboard web paper-trading (baca-only, dari snapshot lokal — tanpa API call)."""
import json
import os
import time
from flask import Flask, render_template, request, redirect, url_for

import config

app = Flask(__name__)
SNAPSHOT_FILE = os.path.join(config.DATA_DIR, 'snapshot.json')
SELL_REQUESTS_FILE = os.path.join(config.DATA_DIR, 'sell_requests.json')

EMPTY = {
    'cash': config.STARTING_CASH, 'coin_value': 0.0, 'total': config.STARTING_CASH,
    'pnl': 0.0, 'pnl_pct': 0.0, 'n_open': 0,
    'positions': [], 'trades': [], 'updated': '-',
}


def load_snapshot():
    try:
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return EMPTY


@app.route('/')
def index():
    s = load_snapshot()
    sold = request.args.get('sold')
    return render_template('dashboard.html', s=s, positions=s['positions'],
                           trades=s['trades'], now=s['updated'], sold=sold,
                           start_cash=config.STARTING_CASH)


@app.route('/sell/<pos_id>', methods=['POST'])
def sell(pos_id):
    """Catat permintaan jual manual — dieksekusi bot di siklus berikutnya."""
    try:
        with open(SELL_REQUESTS_FILE) as f:
            reqs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        reqs = []
    if not any(r.get('pos_id') == pos_id for r in reqs):
        reqs.append({'pos_id': pos_id, 'ts': time.time()})
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(SELL_REQUESTS_FILE, 'w') as f:
        json.dump(reqs, f)
    return redirect(url_for('index', sold=1))


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=config.DASHBOARD_PORT, threaded=True)
