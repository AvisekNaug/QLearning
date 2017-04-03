"""
Tests for the linsim package.
"""

import os
try:
    from flags import FlagGenerator
    from elements import Element
    from elements import BlockInstance
    from elements import ElementMux
    from directives import Directive
    from nodes import Node
    from blocks import Block
    from netlist import Netlist
    from simulate import Simulator
    from system import System
except ImportError:
    from .flags import FlagGenerator
    from .elements import Element
    from elements import BlockInstance
    from .elements import ElementMux
    from .directives import Directive
    from .nodes import Node
    from .blocks import Block
    from .netlist import Netlist
    from .simulate import Simulator
    from .system import System

NUM_TESTS = 0
TESTS_PASSED = 0

def test(func):
    """
    Decorator for test cases.

    Args:
        func (function): A test case function object.
    """
    global NUM_TESTS
    NUM_TESTS += 1
    def test_wrapper(*args, **kwargs):
        """
        Wrapper that calls test function.

        Args:
            desc (str): Description of test.
        """
        print(func.__doc__.strip(), end='\t')
        try:
            func(*args, **kwargs)
            global TESTS_PASSED
            TESTS_PASSED += 1
            print('PASSED')
        except Exception as ex:
            print('FAILED: ' + str(ex))

    return test_wrapper


@test
def test_flag_generator():
    """Test flag generation from states"""

    # Set up
    flags = [4, 3, 2]
    states = 4 * 3 * 2

    # Test 1: Instantiation
    gen = FlagGenerator(*flags)
    assert gen.states == states, "Flag state calculation failed."

    # Test 2: Basis conversion
    assert gen.convert_basis(10, 2, 5) == [1, 0, 1], "Decimal to n-ary failed."
    assert gen.convert_basis(6, 10, (2, 4)) == [1, 6], "N-ary to decimal failed."
    assert gen.convert_basis(2, 8, (1, 0, 1)) == [5], "N-ary to n-ary failed."
    assert gen.convert_basis(10, 2, [1, 0]) == [1, 0, 1, 0], "Decimal to n-ary failed."

    # Test 3: Encoding and decoding
    assert gen.decode(12) == [2, 0, 0], 'Decoding failed.'
    assert gen.encode(*gen.decode(12)) == 12, 'Encoding decoding mismatch.'


@test
def test_node_class():
    """Test node class for hashing"""

    # Set up
    n1 = Node(1)
    n2 = Node(2)
    n1x = Node(1)
    ndict = {}

    # Test 1: Testing hashing into dictionary
    ndict[n1] = 1
    ndict[n2] = 2
    assert ndict.get(n1) == 1, 'Improper node hashing.'
    assert ndict.get(n2) == 2, 'Improper node hashing.'

    # Test 2: Testing retrieval and equality checks
    assert ndict.get(n1x) == ndict.get(n1), 'Node equality failed. Bad hashing.'
    assert n1 == n1.name, 'Node equality failed with strings.'


@test
def test_element_class():
    """Test element class for parsing definitions"""

    # Set up
    def1 = "R100 N1 0 100k"
    def2 = "C25 N1 N2 25e-3"
    def3 = "G1 N3 n2 n1 0 table=(0 1e-1, 10 100)"

    # Test 1: checking definition parsing for default Element class
    elem = Element(definition=def1)
    assert [str(n) for n in elem.nodes] == ['n1', '0'], 'Nodes incorrectly parsed.'
    assert elem.value == '100k', 'Value incorrectly parsed.'

    elem = Element(definition=def2)
    assert [str(n) for n in elem.nodes] == ['n1', 'n2'], 'Nodes incorrectly parsed.'
    assert elem.value == '25e-3', 'Value incorrectly parsed.'

    elem = Element(definition=def3)
    assert [str(n) for n in elem.nodes] == ['n3', 'n2'], 'Nodes incorrectly parsed.'
    assert elem.value == 'n1 0', 'Value incorrectly parsed.'
    # assert hasattr(elem, 'table'), 'Param=Value pair incorrectly parsed.'
    assert elem.param('table') == '(0 1e-1,10 100)', 'Param fetching failed.'
    elem.param('table', '')
    assert elem.param('table') is None, 'Param deletion failed.'

    elem = Element(num_nodes=3, definition=def3)
    assert elem.nodes == ['n3', 'n2', 'n1'], 'Custom node numbers failed.'

    # Test 2: checking argument/keyword parsing for default Element class
    elem = Element('T1', 10, 12, 100, k1=1, K2=2)
    assert str(elem) == 't1 10 12 100 k1=1 k2=2' or \
                        str(elem) == 't1 10 12 100 k2=2 k1=1',\
                        'Arg parsing failed.'


@test
def test_directive_class():
    """Test netlist directive parsing"""

    # Set up
    dir1 = '.tran 0s 10s'
    dir2 = '.ic V(n1)=10 i(10) =500mA'
    dir3 = '.end'

    # Test 1: Instantiation
    ins1 = Directive(definition=dir1)
    ins2 = Directive(definition=dir2)
    ins3 = Directive(definition=dir3)

    # Test 2: Type checking
    assert ins1.kind == 'tran' and ins2.kind == 'ic' and ins3.kind == 'end',\
                        'Incorrect directive types.'

    # Test 3: String conversion
    assert str(ins1) == dir1.lower(), 'Directive string conversion 1 failed.'
    assert str(ins2) == '.ic v(n1)=10 i(10)=500ma' or \
            str(ins2) == '.ic i(10)=500ma v(n1)=10',\
            'Directive string conversion 2 failed.'


@test
def test_element_mux():
    """Test the element multiplexer"""

    # Set up
    class a:
        prefix = 'a'
        def __init__(self, *args, **kwargs):
            pass
    class b(a):
        prefix = 'b'
    class bc(b):
        prefix = 'bc'
    class x(a):
        prefix = 'x'
    def_b = 'b200 blah blah'
    def_bc = 'bcb1 blah blah blah'
    def_a = 'a7 asdjaa alskdj'
    def_other = 'j20 asd knwe'

    # Test 1: Testing mux generation
    mux = ElementMux(root=a, leave=('x',))
    assert set(mux.prefix_list) == set(['b', 'bc']), 'Element mux generation failed.'

    # Test 2: Testing multiplexing
    assert mux.mux(def_b).prefix == 'b', 'Incorrect multiplexing.'
    assert mux.mux(def_bc).prefix == 'bc', 'Incorrect multiplexing.'
    assert mux.mux(def_a).prefix == 'a', 'Incorrect multiplexing.'
    assert mux.mux(def_other).prefix == 'a', 'Incorrect multiplexing.'

    # Test 3: Testing mux editing
    class k(a):
        prefix = 'k'
    mux.add('k', k)
    assert mux.mux('k100 blah blah').prefix == 'k', 'Mux addition failed.'
    mux.remove('k')
    assert ('k' not in mux.prefix_list and 'k' not in mux._mux), \
        'Mux deletion failed.'


@test
def test_block_class():
    """Test block parsing"""

    # Set up
    block1_def = ("E1 1 2 45\n"
                  "E2 2 3 50")
    block1 = ".subckt block1 1 2 n3 n12\n" \
             + block1_def + "\n" \
             + ".ends block1"

    block2_def = ("e3 4 5 100\n"
                  "e4 3 4 whatever")
    block2 = ".subckt block2 1 2 n3 n12\n" \
                + block2_def + "\n" \
                ".ends block2"

    elems1 = "e6 2 4 90\n" \
            + "ELEM45 1 2 64"
    elems2 = "es1 s1 1 10\n" \
            + "es2 s2 3 10k\n" \
            + "es3 s2 s1 1M\n" \
            + "x1 1 2 3 4 BLocK1"

    block_str = block1 + "\n\t" + elems1 + "\n" + block2 + "\n\n" + elems2

    block_repr1 = block1 + "\n" + block2 + "\n" + elems1 + "\n" + elems2
    block_repr2 = block2 + "\n" + block1 + "\n" + elems1 + "\n" + elems2

    block_defs = block_str.split('\n')
    elem = Element(definition='EN1 4 new_node 324k')
    elem_duplicate = Element(definition='E56 2 3 43k')


    # Test 1: Instantiation
    flatten_block = Block('test', ('1', 'n2', 'node3'), block_defs)
    block = Block('test', ('1', 'n2', 'node3'), block_defs)

    # Test 2: Parsing correctness
    assert len(block.blocks) == 2, 'Incorrect number of blocks detected.'
    assert len(block.elements) == 6, 'Block elements not fully populated.'
    b1 = block.blocks.get('block1')
    b2 = block.blocks.get('block2')
    b1_instance = block.elements[block.elements.index('x1')]
    assert b1, 'Nested block key failure.'
    assert b2, 'Nested block key failure.'
    assert b1.name == 'block1', "Nested block name parsing failed."
    assert b2.name == 'block2', "Nested block name parsing failed."
    assert b1.definition == block1_def.lower(), "Nested block def generation failed."
    assert b2.definition == block2_def.lower(), "Nested block def generation failed."
    assert str(b1).strip() == block1.lower(), 'Nested block to string conv failed.'
    assert b1_instance.block.name == 'block1', "Block instance failed."
    assert block.definition == block_repr1.lower() or \
           block.definition == block_repr2.lower(),\
           'Top level block-string conv. failed.'

    # Test 3: Block manipulation
    block.add(elem)
    assert elem in block.elements, 'Element addition failed.'
    assert elem in block.graph[elem.nodes[0]], 'Element addition failed.'
    assert elem in block.graph[elem.nodes[1]], 'Element addition failed.'
    try:
        block.add(elem_duplicate)
    except ValueError:
        pass
    block.remove(elem)
    assert elem not in block.elements, 'Element removal failed.'
    assert elem not in block.graph[elem.nodes[0]], 'Element removal failed.'
    assert block.graph.get(elem.nodes[1]) is None, 'Element removal failed.'

    block.add_block(block)
    assert block in block.blocks, 'Programmatic block addition failed.'
    block.add(block.instance(name='xTest', nodes=('n5', 'n6', 'n7', 'n8')))
    assert 'xtest' in block.elements, 'Programmatic instance addition failed.'
    block.remove_block(block)
    assert block.name not in block.blocks, 'Programmatic block removal failed.'
    assert 'xtest' not in block.elements, 'Programmatic instance removal failed.'

    block.short('s2', 's1')
    assert 's2' not in block.graph, 'Shorted node not removed from block.'
    assert 'es3' not in block.elements, 'Shorted elements not removed.'
    assert len(block.graph['s1']) == 2, 'Incorrect element union after short.'

    # Test 5: block flattening
    flatten_block.flatten()
    assert 'x1' not in flatten_block.elements, 'Flattened block instance not removed.'
    assert len(flatten_block.blocks) == 0, 'Block defs not removed after flattening.'
    assert 'block1_1_e1' in flatten_block.elements, 'Block instance not expanded.'
    assert 'block1_1_e2' in flatten_block.elements, 'Block instance not expanded.'
    assert 'block1_1_3' in flatten_block.graph, 'Internal block node not flattened.'


@test
def test_netlist_class():
    """Test Netlist class for reading/parsing"""

    # Set up
    net = (".model sw sw0\n"
           ".subckt blah 1 2 3\n"
           "r1 1 2 1e10\n"
           "c1 1 3 1e-4\n"
           ".ends blah\n"
           "C1 0 T1 1mF\n"
           "R1 T1 N001 1k\n"
           "G1 N001 0 T1 0 1 table=(0 0,0.1 1m)\n"
           ".ic 0 15s 0 1m uic V(T1)=10V\n"
           ".end")
    net_list = ['* Netlist: test'] + net.lower().split('\n')
    definition = net_list[:9] + net_list[10:]
    tfile = open('test.net', 'w')
    tfile.write(net)
    tfile.close()

    # Test 1: Instantiation/ reading netlist file
    ninstance1 = Netlist('test', netlist=net_list[1:])
    ninstance2 = Netlist('test', path="test.net")

    # Test 2: Parsing netlist
    assert 'subckt' not in ninstance1.directives, 'Non-directives not ignored.'
    assert ninstance1.definition == '\n'.join(definition), 'Incorrect definition.'
    assert str(ninstance1) == '\n'.join(net_list), 'Netlist to str failed.'
    assert str(ninstance2) == '\n'.join(net_list), 'Netlist to str failed.'

    # Finalizing
    os.remove('test.net')


@test
def test_simulator_class():
    """Test circuit simulator"""

    # Set up
    net = ('*Test Circuit',
           'C1 n1 0 1e-6',
           'R1 n2 0 1e3',
           's1 n1 n2 n1 0 switch',
           '.ic V(n1)=10',
           '.model sw switch von=6 voff=5 ron=1 roff=1e6',
           '.end')
    ninstance = Netlist('Test', netlist=net)

    # Test 1: Instantiation and preprocessing
    sim = Simulator(netlist=ninstance, timestep=1e-4)
    assert sim.ic == {'v(n1)':'10'}, 'Initial conditions incorrectly parsed.'

    # Test 2: Running simulation
    res1 = sim.run(duration=1e-3)
    res2 = sim.run(duration=1e-3)
    assert 'v(n1)' in res1, 'Incorrect keys in simulation result.'
    assert res1['v(n1)'] > res2['v(n1)'], 'Simulator state does not persist.'




if __name__ == '__main__':
    print()
    test_flag_generator()
    test_node_class()
    test_element_class()
    test_element_mux()
    test_directive_class()
    test_block_class()
    test_netlist_class()
    test_simulator_class()
    print('\n==========\n')
    print('Tests passed:\t' + str(TESTS_PASSED))
    print('Total tests:\t' + str(NUM_TESTS))
    print()