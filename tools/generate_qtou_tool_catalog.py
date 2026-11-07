#!/usr/bin/env python3
"""Offline catalog generator for qtou tools/list.

Reads the pinned Java sources in tools/qtou_schema_src (commit
877e4ad9eb8f8435c30b55b12949268d0cb24e30) and emits
tools/qtou_tool_catalog.json. It does not contact a network.

Assembly follows the source, not a hand-trimmed name list:
toolDefs(), then the mutations in AgentMcpService (user fields, pages,
assets, evidence, attach file), then AgentRiskMcpPostProcessor
addStrictParam + patchCreateFieldDesc + AgentRiskMcpTools.defs().
evidenceSchema() is built from AgentBpService's static FIELDS and its
object/array/schemaTree/obj helpers. A missing direct dependency stops
the generator with that file name.
"""
import hashlib
import json
import os
import re
import sys

SOURCE_COMMIT = '877e4ad9eb8f8435c30b55b12949268d0cb24e30'
SOURCE_REPOSITORY = 'https://github.com/bitlink0521/qtou'
HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(HERE, 'qtou_schema_src')
CATALOG_PATH = os.path.join(HERE, 'qtou_tool_catalog.json')

PINNED_FILES = (
    ('AgentMcpService.java', 'qtou-api/src/main/java/cn/qtou/api/modules/agent/service/AgentMcpService.java',
     '7656997a66f4f8bcc541e45325aed0527fde12869cf3220fc4e7c0268fee81ea'),
    ('AgentBpService.java', 'qtou-api/src/main/java/cn/qtou/api/modules/agent/service/AgentBpService.java',
     'c32a6b73667e5e3d1ffc243f82a19b4aa94aedaaac3e0e430d00721d73c0dedd'),
    ('AgentBpMediaService.java', 'qtou-api/src/main/java/cn/qtou/api/modules/agent/service/AgentBpMediaService.java',
     'acf855cc82fcd8aedb7ceb8c1b22c426b831a2df40e5db8856de4122403339bc'),
    ('AgentUserFields.java', 'qtou-api/src/main/java/cn/qtou/api/modules/agent/service/AgentUserFields.java',
     '9ab484d1afabf099fbbdae5516316059e69e8418c9969b629a09314b9356e54d'),
    ('AgentEntryFields.java', 'qtou-api/src/main/java/cn/qtou/api/modules/agent/service/AgentEntryFields.java',
     '74d71b99f3c53901b3448759374f2c7dd5e8d942618b6bfabf4d3a178120b123'),
    ('AgentRiskMcpPostProcessor.java', 'qtou-api/src/main/java/cn/qtou/api/modules/agent/service/AgentRiskMcpPostProcessor.java',
     '8c7410dd557d4fc003fcb08a0b3851a6c7ae6398b0cc2f290215bef6d7cfeaa3'),
    ('AgentRiskMcpTools.java', 'qtou-api/src/main/java/cn/qtou/api/modules/agent/service/AgentRiskMcpTools.java',
     'e944a90be987e4542ca19662de91a68d885b988bb7fbadd842af64a41b8dbc7e'),
)


class CatalogSourceError(SystemExit):
    def __init__(self, filename, detail):
        super().__init__('catalog source %s: %s' % (filename, detail))


def fail(filename, detail):
    raise CatalogSourceError(filename, detail)


def read_source(filename):
    path = os.path.join(SOURCE_DIR, filename)
    if not os.path.isfile(path):
        fail(filename, 'missing; direct schema dependency is not in tools/qtou_schema_src')
    return open(path, 'r', encoding='utf-8').read()


def verify_pinned_sources():
    manifest_path = os.path.join(SOURCE_DIR, 'MANIFEST.json')
    if not os.path.isfile(manifest_path):
        fail('MANIFEST.json', 'missing')
    manifest = json.loads(open(manifest_path, 'r', encoding='utf-8').read())
    if manifest.get('commit') != SOURCE_COMMIT or manifest.get('repository') != SOURCE_REPOSITORY:
        fail('MANIFEST.json', 'commit or repository does not match the pinned source')
    listed = [(item.get('file'), item.get('source_path'), item.get('sha256')) for item in manifest.get('files') or []]
    if listed != [(name, path, digest) for name, path, digest in PINNED_FILES]:
        fail('MANIFEST.json', 'file list does not match the pinned sources')
    records = []
    for filename, source_path, expect in PINNED_FILES:
        raw = open(os.path.join(SOURCE_DIR, filename), 'rb').read()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expect:
            fail(filename, 'sha256 %s != pinned %s' % (digest, expect))
        records.append({'path': source_path, 'sha256': digest})
    return records


def catalog_tools_digest(tools):
    raw = json.dumps(tools, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def skip(text, index):
    length = len(text)
    while index < length:
        char = text[index]
        if char in ' \t\r\n':
            index += 1
            continue
        if text.startswith('//', index):
            newline = text.find('\n', index)
            index = length if newline < 0 else newline + 1
            continue
        if text.startswith('/*', index):
            end = text.find('*/', index + 2)
            if end < 0:
                fail('java', 'unterminated block comment')
            index = end + 2
            continue
        break
    return index


def parse_java_string(text, index, filename):
    if index >= len(text) or text[index] != '"':
        fail(filename, 'expected a string at %d' % index)
    index += 1
    chars = []
    while index < len(text):
        char = text[index]
        if char == '\\':
            if index + 1 >= len(text):
                fail(filename, 'truncated string escape')
            mapping = {'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\'}
            chars.append(mapping.get(text[index + 1], text[index + 1]))
            index += 2
            continue
        if char == '"':
            return ''.join(chars), index + 1
        chars.append(char)
        index += 1
    fail(filename, 'unterminated string')


def parse_concat_string(text, index, filename):
    value, index = parse_java_string(text, index, filename)
    while True:
        index = skip(text, index)
        if index < len(text) and text[index] == '+':
            index = skip(text, index + 1)
            nxt, index = parse_java_string(text, index, filename)
            value += nxt
            continue
        return value, index


def match_paren(text, open_index, filename):
    depth = 0
    index = open_index
    while index < len(text):
        if text[index] == '"':
            _, index = parse_java_string(text, index, filename)
            continue
        if text.startswith('//', index):
            newline = text.find('\n', index)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith('/*', index):
            end = text.find('*/', index + 2)
            index = len(text) if end < 0 else end + 2
            continue
        if text[index] == '(':
            depth += 1
        elif text[index] == ')':
            depth -= 1
            if depth == 0:
                return index
        index += 1
    fail(filename, 'unbalanced parenthesis at %d' % open_index)


def method_body(source, signature, filename):
    start = source.find(signature)
    if start < 0:
        fail(filename, 'missing %s' % signature)
    brace = source.find('{', start)
    if brace < 0:
        fail(filename, 'missing body for %s' % signature)
    depth = 0
    index = brace
    while index < len(source):
        if source[index] == '"':
            _, index = parse_java_string(source, index, filename)
            continue
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[brace + 1:index]
        index += 1
    fail(filename, 'unbalanced body for %s' % signature)


def java_string_constant(source, name, filename):
    marker = 'static final String %s = ' % name
    start = source.find(marker)
    if start < 0:
        fail(filename, 'missing constant %s' % name)
    value, _ = parse_concat_string(source, skip(source, start + len(marker)), filename)
    return value


def string_list_expr(source, marker, filename):
    start = source.find(marker)
    if start < 0:
        fail(filename, 'missing %s' % marker)
    list_at = source.find('Arrays.asList(', start)
    if list_at < 0 or list_at - start > 180:
        fail(filename, 'expected Arrays.asList after %s' % marker)
    open_index = list_at + len('Arrays.asList')
    close = match_paren(source, open_index, filename)
    values = []
    cursor = open_index + 1
    while cursor < close:
        cursor = skip(source, cursor)
        if cursor >= close:
            break
        if source[cursor] == ',':
            cursor += 1
            continue
        if source[cursor] != '"':
            fail(filename, 'expected string in %s' % marker)
        value, cursor = parse_concat_string(source, cursor, filename)
        values.append(value)
    return values


def parse_schema_args(text, start, end, filename):
    args = []
    index = start
    while index < end:
        index = skip(text, index)
        if index >= end:
            break
        if text[index] == ',':
            index += 1
            continue
        if text[index] == '"':
            value, index = parse_concat_string(text, index, filename)
            args.append(value)
            continue
        if text.startswith('true', index) and not text[index + 4:index + 5].isalnum():
            args.append(True)
            index += 4
            continue
        if text.startswith('false', index) and not text[index + 5:index + 6].isalnum():
            args.append(False)
            index += 5
            continue
        fail(filename, 'unsupported schema argument near %r' % text[index:index + 40])
    if len(args) % 4:
        fail(filename, 'schema arguments are not groups of name,type,description,required')
    return args


def schema(props):
    properties = {}
    required = []
    for index in range(0, len(props), 4):
        name, kind, description, flag = props[index:index + 4]
        properties[name] = {'type': kind, 'description': description}
        if flag is True or (isinstance(flag, str) and flag.lower() == 'true'):
            required.append(name)
    result = {'type': 'object', 'properties': properties}
    if required:
        result['required'] = required
    return result


def schema_string(description):
    return {'type': 'string', 'description': description}


def tool(name, description, input_schema):
    return {'name': name, 'description': description, 'inputSchema': input_schema}


def parse_tool_defs(source):
    filename = 'AgentMcpService.java'
    body = method_body(source, 'private List<Map<String, Object>> toolDefs()', filename)
    expected = len(re.findall(r'tools\.add\(tool\(', body))
    tools = []
    cursor = 0
    while True:
        found = body.find('tools.add(tool(', cursor)
        if found < 0:
            break
        open_index = found + len('tools.add(tool')
        close = match_paren(body, open_index, filename)
        args = []
        index = open_index + 1
        while index < close:
            index = skip(body, index)
            if index >= close:
                break
            if body[index] == ',':
                index += 1
                continue
            if body[index] == '"':
                value, index = parse_concat_string(body, index, filename)
                args.append(value)
                continue
            if body.startswith('schema(', index):
                schema_open = index + len('schema')
                schema_close = match_paren(body, schema_open, filename)
                args.append(schema(parse_schema_args(body, schema_open + 1, schema_close, filename)))
                index = schema_close + 1
                continue
            if body.startswith('createAlertSchema()', index):
                args.append(('createAlert',))
                index += len('createAlertSchema()')
                continue
            fail(filename, 'unsupported toolDefs argument near %r' % body[index:index + 60])
        if len(args) != 3 or not isinstance(args[0], str) or not isinstance(args[1], str):
            fail(filename, 'tool() did not parse as name, description, schema')
        if args[2] == ('createAlert',):
            input_schema = ('createAlert',)
        elif isinstance(args[2], dict):
            input_schema = args[2]
        else:
            fail(filename, 'tool %s has no schema' % args[0])
        tools.append(tool(args[0], args[1], input_schema))
        cursor = close + 1
    if len(tools) != expected or not tools:
        fail(filename, 'parsed %d toolDefs, source has %d tools.add(tool(' % (len(tools), expected))
    return tools


def create_alert_schema(source):
    filename = 'AgentMcpService.java'
    body = method_body(source, 'private static Map<String, Object> createAlertSchema()', filename)
    marker = 'schema('
    start = body.find(marker)
    if start < 0:
        fail(filename, 'createAlertSchema has no schema(')
    close = match_paren(body, start + len('schema') - 1, filename)
    result = schema(parse_schema_args(body, start + len(marker), close, filename))
    rows = re.findall(r'\{\s*"((?:\\.|[^"\\])*)"\s*,\s*"((?:\\.|[^"\\])*)"\s*\}', body)
    if len(rows) != 8:
        fail(filename, 'createAlertSchema source rows parsed %d, expected 8' % len(rows))
    properties = {}
    for name, description in rows:
        properties[name] = {'type': 'string', 'description': description}
    description_at = body.find('src.put("description",')
    if description_at < 0:
        fail(filename, 'createAlertSchema sources description missing')
    description, _ = parse_concat_string(body, skip(body, description_at + len('src.put("description",')), filename)
    item = {'type': 'object', 'properties': properties}
    result['properties']['sources'] = {'type': 'array', 'description': description, 'items': item}
    result['required'].append('sources')
    return result


def parse_fields(source):
    filename = 'AgentBpService.java'
    start = source.find('private static final Map<String,Map<String,Object>> FIELDS=')
    if start < 0:
        fail(filename, 'missing FIELDS')
    static_at = source.find('static {', start)
    if static_at < 0:
        fail(filename, 'missing FIELDS static block')
    brace = source.find('{', static_at)
    depth = 0
    index = brace
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                block = source[brace + 1:index]
                break
        index += 1
    else:
        fail(filename, 'unbalanced FIELDS static block')
    fields = []
    for match in re.finditer(r'add\("((?:\\.|[^"\\])*)","((?:\\.|[^"\\])*)","((?:\\.|[^"\\])*)","((?:\\.|[^"\\])*)","((?:\\.|[^"\\])*)"\);', block):
        scope, key, label, kind, dictionary = match.groups()
        fields.append((scope + '.' + key, {
            'field': scope + '.' + key,
            'property': key,
            'scope': scope,
            'label': label,
            'type': kind,
            'dictionary': dictionary,
            'writeMode': 'missing_only',
            'uiVisibility': '由租户开关决定；字段仍可发现并回读',
        }))
    if not fields:
        fail(filename, 'FIELDS static block parsed no add() calls')
    return fields


def obj(*pairs):
    return {pairs[index]: pairs[index + 1] for index in range(0, len(pairs), 2)}


def schema_tree(value):
    if isinstance(value, dict):
        return {str(key): schema_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [schema_tree(item) for item in value]
    return value


def object_schema(properties, *required):
    return obj('type', 'object', 'properties', properties, 'required', list(required), 'additionalProperties', False)


def array_schema(items):
    return obj('type', 'array', 'items', items)


def evidence_schema(bp_source, field_keys):
    filename = 'AgentBpService.java'
    body = method_body(bp_source, 'public static Map<String,Object> evidenceSchema()', filename)
    for token in ('schemaTree(object(', 'FIELDS.keySet()', 'schemaVersion', 'reviewed', 'document'):
        if token not in body:
            fail(filename, 'evidenceSchema missing %s' % token)
    if 'additionalProperties",false' not in bp_source or 'private static Map<String,Object> object(' not in bp_source:
        fail(filename, 'object() helper that sets additionalProperties is missing')
    if 'private static Object schemaTree(' not in bp_source or 'static Map<String,Object> obj(' not in bp_source:
        fail(filename, 'schemaTree or obj helper is missing')
    if 'private static Map<String,Object> array(' not in bp_source:
        fail(filename, 'array() helper is missing')
    nature = re.search(r'Arrays\.asList\("historical_fact","plan","forecast","current_fact"\)', body)
    mode = re.search(r'Arrays\.asList\("fill_missing","append_evidence"\)', body)
    team_keys = re.search(r'Arrays\.asList\("name","jop","introduction","education","workExperience","exclusiveResources","telephone","weChat","businessJob"\)', body)
    if not nature or not mode or not team_keys:
        fail(filename, 'evidenceSchema enum or team keys not found')
    as_of_field = '与document.asOf相同的披露时点；document.asOf为空时也留空'
    as_of_document = 'BP披露日期YYYY-MM或YYYY-MM-DD；材料未注明时留空，不用文件导出日期冒充'
    value_desc = '金额必须标明万元；字典传标签；无证据不提供'
    mode_desc = '默认fill_missing；append_evidence只允许描述字段补充遗漏证据，保留原文并去重，须已有补全授权'
    finance_desc = '带历史时间及事实/计划性质，不将预测写实际财务'
    for snippet in (as_of_field, as_of_document, value_desc, mode_desc, finance_desc):
        if snippet not in body:
            fail(filename, 'evidenceSchema text missing: %s' % snippet)
    ref = object_schema(obj(
        'page', obj('type', 'integer', 'minimum', 1),
        'quote', obj('type', 'string', 'minLength', 5, 'maxLength', 4000),
    ), 'page', 'quote')
    refs = array_schema(ref)
    temporal = obj(
        'nature', obj('type', 'string', 'enum', ['historical_fact', 'plan', 'forecast', 'current_fact']),
        'asOf', obj('type', 'string', 'description', as_of_field),
        'sources', refs,
    )
    field = dict(temporal)
    field['field'] = obj('type', 'string', 'enum', list(field_keys))
    field['value'] = obj('type', 'string', 'description', value_desc)
    field['mode'] = obj('type', 'string', 'enum', ['fill_missing', 'append_evidence'], 'description', mode_desc)
    team = dict(temporal)
    for key in ['name', 'jop', 'introduction', 'education', 'workExperience', 'exclusiveResources', 'telephone', 'weChat', 'businessJob']:
        team[key] = obj('type', 'string')
    team['stockRate'] = obj('type', 'number', 'minimum', 0, 'maximum', 100)
    team['seatNum'] = obj('type', 'integer', 'minimum', 0, 'maximum', 100)
    finance = dict(temporal)
    finance['historyFinancing'] = obj('type', 'string', 'description', finance_desc)
    competitor = dict(temporal)
    competitor['name'] = obj('type', 'string')
    competitor['description'] = obj('type', 'string')
    page = object_schema(obj('page', obj('type', 'integer', 'minimum', 1), 'text', obj('type', 'string')), 'page', 'text')
    document = object_schema(obj(
        'name', obj('type', 'string'),
        'asOf', obj('type', 'string', 'description', as_of_document),
        'pages', array_schema(page),
    ), 'name', 'pages')
    return schema_tree(object_schema(obj(
        'schemaVersion', obj('type', 'integer', 'enum', [1]),
        'reviewed', obj('type', 'boolean', 'enum', [True]),
        'document', document,
        'fields', array_schema(object_schema(field, 'field', 'value', 'nature', 'asOf', 'sources')),
        'team', array_schema(object_schema(team, 'name', 'nature', 'asOf', 'sources')),
        'financing', array_schema(object_schema(finance, 'historyFinancing', 'nature', 'asOf', 'sources')),
        'competitors', array_schema(object_schema(competitor, 'name', 'nature', 'asOf', 'sources')),
    ), 'schemaVersion', 'reviewed', 'document'))


def asset_schema(source):
    filename = 'AgentBpMediaService.java'
    body = method_body(source, 'public static Map<String,Object> assetSchema()', filename)
    for token in ('"project.logo"', '"team.photo"', '"document.image"', '"minItems",1', '"maxItems",8', '"additionalProperties",false'):
        if token not in body:
            fail(filename, 'assetSchema missing %s' % token)
    return obj(
        'type', 'array', 'minItems', 1, 'maxItems', 8,
        'items', obj(
            'type', 'object',
            'properties', obj(
                'target', obj('type', 'string', 'enum', ['project.logo', 'team.photo', 'document.image']),
                'page', obj('type', 'integer', 'minimum', 1),
                'bbox', obj('type', 'array', 'minItems', 4, 'maxItems', 4, 'items', obj('type', 'number', 'minimum', 0, 'maximum', 1)),
                'memberId', obj('type', 'string'),
                'name', obj('type', 'string'),
                'reason', obj('type', 'string', 'minLength', 1, 'maxLength', 500),
                'reviewed', obj('type', 'boolean', 'enum', [True]),
            ),
            'required', ['target', 'page', 'bbox', 'reason', 'reviewed'],
            'additionalProperties', False,
        ),
    )


def pages_schema():
    return {
        'type': 'array',
        'minItems': 1,
        'maxItems': 2,
        'items': {'type': 'integer', 'minimum': 1},
    }


def file_schema(mcp_source):
    filename = 'AgentMcpService.java'
    for snippet in ('PDF文件名，不含路径', '真实PDF内容base64，不超过20MB', '可选文件SHA256'):
        if snippet not in mcp_source:
            fail(filename, 'attach file schema text missing: %s' % snippet)
    return {
        'type': 'object',
        'properties': {
            'fileName': schema_string('PDF文件名，不含路径'),
            'contentBase64': schema_string('真实PDF内容base64，不超过20MB'),
            'sha256': schema_string('可选文件SHA256'),
        },
        'required': ['fileName', 'contentBase64'],
        'additionalProperties': False,
    }


def apply_tooldef_mutations(tools, mcp_source, user_source, entry_source, evidence, assets):
    keys = string_list_expr(user_source, 'static final List<String> KEYS = ', 'AgentUserFields.java')
    labels = {}
    for match in re.finditer(r'LABELS\.put\("((?:\\.|[^"\\])*)", "((?:\\.|[^"\\])*)"\);', entry_source):
        labels[match.group(1)] = match.group(2)
    if not keys or not labels:
        fail('AgentUserFields.java' if not keys else 'AgentEntryFields.java', 'KEYS or LABELS missing')
    for key in keys:
        if key not in labels:
            fail('AgentEntryFields.java', 'LABELS missing key %s' % key)
    mutated = False
    for definition in tools:
        if definition['name'] != 'agent_projects_user_fields':
            continue
        properties = definition['inputSchema']['properties']
        properties['statement']['minLength'] = 2
        properties['statement']['maxLength'] = 2000
        allowed = {}
        for key in keys:
            allowed[key] = schema_string(labels[key])
        fields = properties['fields']
        fields['properties'] = allowed
        fields['additionalProperties'] = False
        fields['minProperties'] = 1
        mutated = True
    if not mutated:
        fail('AgentMcpService.java', 'agent_projects_user_fields missing')
    if 'pg.put("minItems",1)' not in mcp_source or 'pg.put("maxItems",2)' not in mcp_source:
        fail('AgentMcpService.java', 'pages schema mutation missing')
    for definition in tools:
        name = definition['name']
        properties = definition['inputSchema']['properties']
        if name == 'agent_projects_bp_assets':
            properties['assets'] = assets
        if name in ('agent_projects_bp_pages', 'agent_documents_pages'):
            properties['pages'] = pages_schema()
    for definition in tools:
        name = definition['name']
        properties = definition['inputSchema']['properties']
        if name == 'agent_projects_bp_fill':
            properties['evidence'] = evidence
        if name == 'agent_projects_create_pending':
            properties['bpEvidence'] = evidence
        if name == 'agent_projects_bp_attach':
            properties['file'] = file_schema(mcp_source)
    return keys


def parse_risk_rows(body, start, filename):
    if not body.startswith('new Object[][]', start):
        fail(filename, 'risk tool properties are not new Object[][]')
    index = skip(body, start + len('new Object[][]'))
    if body[index] != '{':
        fail(filename, 'risk tool properties missing brace')
    index += 1
    rows = []
    while index < len(body):
        index = skip(body, index)
        if body[index] == '}':
            return rows, index + 1
        if body[index] == ',':
            index += 1
            continue
        if body[index] != '{':
            fail(filename, 'risk property row missing brace near %r' % body[index:index + 40])
        index += 1
        cells = []
        while index < len(body):
            index = skip(body, index)
            if body[index] == '}':
                index += 1
                break
            if body[index] == ',':
                index += 1
                continue
            if body[index] == '"':
                value, index = parse_concat_string(body, index, filename)
                cells.append(value)
                continue
            match = re.match(r'[A-Za-z_][A-Za-z0-9_]*', body[index:])
            if not match:
                fail(filename, 'risk property cell near %r' % body[index:index + 40])
            cells.append(('ident', match.group(0)))
            index += len(match.group(0))
        rows.append(cells)
    fail(filename, 'unterminated risk property rows')


def risk_defs(source):
    filename = 'AgentRiskMcpTools.java'
    names = string_list_expr(source, 'public static final List<String> NAMES = ', filename)
    body = method_body(source, 'public static List<Map<String, Object>> defs()', filename)
    tools = []
    cursor = 0
    while True:
        found = body.find('l.add(tool(', cursor)
        if found < 0:
            break
        open_index = found + len('l.add(tool')
        close = match_paren(body, open_index, filename)
        index = open_index + 1
        index = skip(body, index)
        name, index = parse_concat_string(body, index, filename)
        index = skip(body, index)
        if body[index] != ',':
            fail(filename, 'risk tool %s missing comma after name' % name)
        index = skip(body, index + 1)
        description, index = parse_concat_string(body, index, filename)
        index = skip(body, index)
        if body[index] != ',':
            fail(filename, 'risk tool %s missing properties' % name)
        index = skip(body, index + 1)
        rows, index = parse_risk_rows(body, index, filename)
        required = []
        while index < close:
            index = skip(body, index)
            if index >= close:
                break
            if body[index] == ',':
                index += 1
                continue
            if body[index] != '"':
                fail(filename, 'risk tool %s required name near %r' % (name, body[index:index + 30]))
            value, index = parse_concat_string(body, index, filename)
            required.append(value)
        properties = {}
        for cells in rows:
            if len(cells) < 3 or not all(isinstance(cell, str) for cell in cells[:3]):
                fail(filename, 'risk tool %s row is not name,type,description' % name)
            prop = {'type': cells[1], 'description': cells[2]}
            if len(cells) > 3:
                ident = cells[3][1] if isinstance(cells[3], tuple) else None
                if ident == 'obj':
                    prop['items'] = {'type': 'object'}
                elif ident == 'str':
                    prop['items'] = {'type': 'string'}
                else:
                    fail(filename, 'risk tool %s items ident %r is not obj or str' % (name, cells[3]))
            properties[cells[0]] = prop
        input_schema = {'type': 'object', 'properties': properties}
        if required:
            input_schema['required'] = required
        tools.append(tool(name, description, input_schema))
        cursor = close + 1
    if [item['name'] for item in tools] != names:
        fail(filename, 'defs() names %s != NAMES %s' % ([item['name'] for item in tools], names))
    return tools


def apply_post_processor(tools, source, risk_tools):
    filename = 'AgentRiskMcpPostProcessor.java'
    body = method_body(source, 'Object around(Map<String, Object> agent, String body, MethodInvocation mi) throws Throwable', filename)
    for token in ('addStrictParam(all)', 'patchCreateFieldDesc(all)', 'AgentRiskMcpTools.defs()'):
        if token not in body:
            fail(filename, 'tools/list assembly missing %s' % token)
    field_desc = java_string_constant(source, 'FIELD_DESC', filename)
    sources_add = java_string_constant(source, 'SOURCES_DESC_ADD', filename)
    if 'd + "；" + SOURCES_DESC_ADD' not in source:
        fail(filename, 'sources description join is not the source expression')
    strict = '可选，默认 false。true 时只留 is_after_invest=1 且未删的项目（场景③巡检用）'
    if strict not in source:
        fail(filename, 'strictAfterInvest description missing')
    for definition in tools:
        if definition['name'] != 'agent_portfolio_list':
            continue
        definition['inputSchema']['properties']['strictAfterInvest'] = {'type': 'boolean', 'description': strict}
    patched = False
    for definition in tools:
        if definition['name'] != 'agent_risk_alerts_create':
            continue
        props = definition['inputSchema']['properties']
        src = dict(props['sources'])
        current = src.get('description') or ''
        if not str(current).endswith(sources_add):
            src['description'] = sources_add if not current else current + '；' + sources_add
        item = dict(src['items'])
        item_props = dict(item['properties'])
        field = dict(item_props.get('field') or {})
        if 'type' not in field:
            field['type'] = 'string'
        field['description'] = field_desc
        item_props['field'] = field
        item['properties'] = item_props
        src['items'] = item
        props['sources'] = src
        patched = True
    if not patched:
        fail(filename, 'agent_risk_alerts_create missing for patchCreateFieldDesc')
    return tools + risk_tools


def build_tools():
    records = verify_pinned_sources()
    mcp = read_source('AgentMcpService.java')
    bp = read_source('AgentBpService.java')
    media = read_source('AgentBpMediaService.java')
    users = read_source('AgentUserFields.java')
    entry = read_source('AgentEntryFields.java')
    post = read_source('AgentRiskMcpPostProcessor.java')
    risk = read_source('AgentRiskMcpTools.java')
    if 'import cn.qtou.console.sys.utils.DictUtils;' in bp and 'DictUtils' in method_body(bp, 'public static Map<String,Object> evidenceSchema()', 'AgentBpService.java'):
        fail('DictUtils', 'evidenceSchema references DictUtils but that file is not in the pinned sources')
    tools = parse_tool_defs(mcp)
    for definition in tools:
        if definition['inputSchema'] == ('createAlert',):
            definition['inputSchema'] = create_alert_schema(mcp)
    fields = parse_fields(bp)
    evidence = evidence_schema(bp, [key for key, _ in fields])
    apply_tooldef_mutations(tools, mcp, users, entry, evidence, asset_schema(media))
    tools = apply_post_processor(tools, post, risk_defs(risk))
    names = [item['name'] for item in tools]
    if len(names) != len(set(names)):
        fail('AgentMcpService.java', 'duplicate tool name in assembled catalog')
    for item in tools:
        if not isinstance(item.get('inputSchema'), dict) or not isinstance(item.get('description'), str):
            fail('AgentMcpService.java', 'tool %s is missing description or inputSchema' % item.get('name'))
    return records, tools


def catalog_document(records, tools):
    generator = os.path.abspath(__file__)
    return {
        'sourceRepository': SOURCE_REPOSITORY,
        'sourceCommit': SOURCE_COMMIT,
        'sourceFiles': records,
        'generator': 'tools/generate_qtou_tool_catalog.py',
        'generatorSha256': hashlib.sha256(open(generator, 'rb').read()).hexdigest(),
        'schemaSha256': catalog_tools_digest(tools),
        'tools': tools,
    }


def render(document):
    return json.dumps(document, ensure_ascii=False, indent=2) + '\n'


def main():
    records, tools = build_tools()
    document = catalog_document(records, tools)
    text = render(document)
    if '--stdout' in sys.argv:
        sys.stdout.write(text)
        return
    destination = CATALOG_PATH
    for arg in sys.argv[1:]:
        if arg.startswith('--output='):
            destination = arg.split('=', 1)[1]
    with open(destination, 'w', encoding='utf-8') as handle:
        handle.write(text)
    print('tools %d schemaSha256 %s' % (len(tools), document['schemaSha256']))


if __name__ == '__main__':
    main()
