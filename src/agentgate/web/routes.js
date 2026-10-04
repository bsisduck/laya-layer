// Public hash compatibility; only these three groups are primary destinations.
export const destinations = {
  chat: [['#chat', 'Example conversations'], ['#hr', 'Live HR workspace'], ['#approvals', 'Approvals'], ['#outbox', 'Test outbox'], ['#playground', 'Playground']],
  logs: [['#logs', 'Security timeline'], ['#overview', 'Operations'], ['#overview?section=usage', 'Department usage'], ['#export', 'Audit export']],
  workflow: [['#workflow', 'Pipeline'], ['#catalog', 'Catalog'], ['#policy', 'Policy studio'], ['#feed', 'Threat feed'], ['#overview?section=standards', 'Standards evidence'], ['#overview?section=controls', 'Threat controls']],
};
export function resolveRoute(hash = '') {
  const [raw, query = ''] = hash.replace(/^#/, '').split('?');
  const name = ['chat', 'logs', 'workflow', 'hr', 'approvals', 'outbox', 'playground', 'overview', 'timeline', 'export', 'catalog', 'policy', 'feed'].includes(raw) ? raw : 'chat';
  const requested = new URLSearchParams(query).get('section');
  const section = name === 'overview' && ['usage', 'standards', 'controls'].includes(requested) ? requested : 'all';
  const parent = ['catalog', 'policy', 'feed', 'workflow'].includes(name) || ['standards', 'controls'].includes(section) ? 'workflow' : ['logs', 'timeline', 'overview', 'export'].includes(name) ? 'logs' : 'chat';
  const active = name === 'overview' && section !== 'all' ? `#overview?section=${section}` : name === 'timeline' ? '#logs' : `#${name}`;
  return {name, parent, section, active};
}
