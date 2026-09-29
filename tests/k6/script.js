import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const reqRate = new Rate('http_req_rate');

export const options = {
    scenarios: {
        load: {
            executor: 'ramping-arrival-rate',
            startRate: 2,
            timeUnit: '1s',
            preAllocatedVUs: 10,
            stages: [
                { target: 15, duration: '30s' },
                { target: 0, duration: '15s' },
            ],
        },
    },
    thresholds: {
        'checks': ['rate>0.95'],
        'http_req_duration': ['p(95)<800'],
    },
};

export default function () {
    const params = {
        headers: {
            'Host': 'rollsafe.local',
            'Content-Type': 'application/json',
            'User-Agent': 'k6-loadtester/rollsafe',
        },
    };

    const res = http.get('http://localhost:8080/success', params);
    
    check(res, {
        'status is 200': (r) => r.status === 200,
        'deployment recognized': (r) => {
            try {
                const json = r.json();
                return ['stable', 'canary'].includes(json.deployment);
            } catch (e) {
                return false;
            }
        },
    });

    sleep(0.1);
}
