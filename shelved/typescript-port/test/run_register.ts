import { run } from '../src/calibrate.js';
const seasons = Number(process.argv[2] ?? 1);
run('/home/claude/data/league_seed_2026.csv', seasons);
