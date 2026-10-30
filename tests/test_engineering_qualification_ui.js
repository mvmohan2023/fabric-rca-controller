// Offline DOM harness for the actual qualification renderer; no browser or lab.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('webui/app.js', 'utf8');
const escape = source.slice(source.indexOf('function escapeHtml('), source.indexOf('function formatPct('));
const renderer = source.slice(source.indexOf('async function loadEngineeringQualification('), source.indexOf('async function loadCase('));
function setup(fetchJson) {
  const block = {textContent: '', innerHTML: ''};
  const context = {state: {currentRunId: 'baseline'}, fetchJson,
                   document: {getElementById: () => block}};
  vm.createContext(context);
  vm.runInContext(escape + renderer, context);
  return {block, context};
}
(async () => {
  let passed = 0;
  {
    const {block, context} = setup(async () => ({engineering_assessment: {
      scoped_fabric_collection: {status: 'loaded', phase_record_counts: {pre: 0, running: 4}, limitations: ['derived only']},
      intent_path_coverage: {status: 'unassessed_path_coverage', reasons: ['src_leaf_unresolved']},
      aligned_conflict_assessment: {status: 'not_assessed_without_aligned_measurement_windows', comparable_pair_count: 0}
    }}));
    await context.loadEngineeringQualification('baseline');
    assert.ok(block.innerHTML.includes('pre: 0 scoped records'));
    assert.ok(block.innerHTML.includes('src_leaf_unresolved'));
    assert.ok(block.innerHTML.includes('Comparable pairs: 0'));
    passed++;
  }
  {
    const {block, context} = setup(async () => {throw new Error('404');});
    await context.loadEngineeringQualification('baseline');
    assert.ok(block.textContent.includes('unavailable'));
    assert.ok(block.textContent.includes('coverage gap'));
    passed++;
  }
  {
    const {block, context} = setup(async () => ({engineering_assessment: {ui_claim_qualification: {
      findings: [{section: '<script>alert(1)</script>', interpretation: '<img onerror=bad()>', supporting_artifact: 'x'}]
    }}}));
    await context.loadEngineeringQualification('baseline');
    assert.ok(!block.innerHTML.includes('<script>'));
    assert.ok(!block.innerHTML.includes('<img onerror'));
    assert.ok(block.innerHTML.includes('&lt;script&gt;'));
    passed++;
  }
  {
    let finish;
    const {block, context} = setup(() => new Promise(resolve => {finish = resolve;}));
    const pending = context.loadEngineeringQualification('baseline');
    context.state.currentRunId = 'another-case';
    block.innerHTML = 'newer case';
    finish({engineering_assessment: {}});
    await pending;
    assert.equal(block.innerHTML, 'newer case');
    passed++;
  }
  {
    const {block, context} = setup(async () => ({engineering_assessment: {roce_snapshot_qualification: {
      status: 'snapshot_differences_only', source_availability: {pre: {path: '/root/artifacts/campaigns/run/pre.json'}},
      flow_count: 1, flows: [{flow_identity: {flow_name: 'Flow84', src_qp: 66, dest_qp: 66},
      snapshot_differences: {seqerror: {pre: 82, post: 74248, increase: 74166}},
      comparison_coverage: {counter_continuity: 'unverified', duplicate_coverage: {pre: {row_count: 84}}}}]
    }}}));
    await context.loadEngineeringQualification('baseline');
    assert.ok(block.innerHTML.includes('/artifacts/campaigns/run/pre.json'));
    assert.ok(block.innerHTML.includes('74166'));
    assert.ok(block.innerHTML.includes('unverified'));
    passed++;
  }
  process.stdout.write(`${passed} qualification UI cases PASS\n`);
})().catch(error => {process.stderr.write(String(error.stack)); process.exit(1);});
