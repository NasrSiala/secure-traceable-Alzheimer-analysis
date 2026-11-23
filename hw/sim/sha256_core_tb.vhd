-- sha256_core_tb: self-checking VHDL-2008 testbench of sha256_core (T3.18, 1/2, AC-15.1).
--
-- Run it in Vivado xsim (`make -C hw/sim xsim`, or by hand: xvhdl --2008 ..., xelab, xsim -runall).
-- It prints "SHA256_TB PASSED" at the end, and stops with a failure at the first wrong answer.
-- The reference run of the project is the cocotb bench (hw/sim/test_sha256.py, GHDL), which
-- compares with hashlib; this testbench carries the FIPS 180-4 digests as literals instead, and
-- tests/scripts/test_sha256_core.py checks every literal against hashlib.
--
-- The core does not pad: this testbench pads (FIPS 180-4 5.1.1) before it feeds the words.
--
-- What it checks:
--   - "abc", the 448-bit and the 896-bit messages (AC-15.1): one and two blocks, so the chaining
--     of H from a block to the next is covered;
--   - the same messages one after the other, with no pause between them;
--   - the block duration: busy lasts BLOCK_CYCLES clock cycles and done follows at once;
--   - word_ready is low while busy; done is cleared by init;
--   - recovery after a reset during the load of a block and during the rounds.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sha256_core_tb is
end entity sha256_core_tb;

architecture sim of sha256_core_tb is
  constant CLK_PERIOD   : time    := 10 ns;
  -- 64 round cycles and one cycle to add the working variables to H.
  constant BLOCK_CYCLES : natural := 65;

  constant MSG_ABC    : string := "abc";
  constant DIGEST_ABC : std_logic_vector(255 downto 0) :=
    x"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

  constant MSG_M448    : string := "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
  constant DIGEST_M448 : std_logic_vector(255 downto 0) :=
    x"248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1";

  constant MSG_M896    : string := "abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu";
  constant DIGEST_M896 : std_logic_vector(255 downto 0) :=
    x"cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1";

  -- FIPS 180-4 5.3.3, the value of H after a reset or an init.
  constant DIGEST_H0 : std_logic_vector(255 downto 0) :=
    x"6a09e667bb67ae853c6ef372a54ff53a510e527f9b05688c1f83d9ab5be0cd19";

  type byte_array is array (natural range <>) of natural range 0 to 255;

  signal aclk       : std_logic := '0';
  signal aresetn    : std_logic := '0';
  signal init       : std_logic := '0';
  signal word_valid : std_logic := '0';
  signal word_data  : std_logic_vector(31 downto 0) := (others => '0');
  signal word_ready : std_logic;
  signal busy       : std_logic;
  signal done       : std_logic;
  signal digest     : std_logic_vector(255 downto 0);

  signal cycle    : natural := 0;
  signal finished : boolean := false;

  -- FIPS 180-4 5.1.1: the message, a 1 bit, zeros, and the length in bits on 64 bits.
  function padded (msg : string) return byte_array is
    constant blocks : natural := (msg'length + 9 + 63) / 64;
    variable bytes  : byte_array(0 to blocks * 64 - 1) := (others => 0);
    variable bits   : unsigned(63 downto 0);
  begin
    for i in msg'range loop
      bytes(i - msg'low) := character'pos(msg(i));
    end loop;
    bytes(msg'length) := 16#80#;
    bits := to_unsigned(msg'length * 8, 64);
    for i in 0 to 7 loop
      bytes(bytes'length - 8 + i) := to_integer(bits(63 - 8 * i downto 56 - 8 * i));
    end loop;
    return bytes;
  end function;
begin
  clock : process
  begin
    while not finished loop
      aclk <= '0';
      wait for CLK_PERIOD / 2;
      aclk <= '1';
      wait for CLK_PERIOD / 2;
    end loop;
    wait;
  end process;

  counter : process (aclk)
  begin
    if rising_edge(aclk) then
      cycle <= cycle + 1;
    end if;
  end process;

  dut : entity work.sha256_core
    port map (
      aclk       => aclk,
      aresetn    => aresetn,
      init       => init,
      word_valid => word_valid,
      word_data  => word_data,
      word_ready => word_ready,
      busy       => busy,
      done       => done,
      digest     => digest
    );

  stimulus : process
    variable accepted_at : natural;

    procedure tick (n : natural := 1) is
    begin
      for i in 1 to n loop
        wait until rising_edge(aclk);
      end loop;
    end procedure;

    procedure pulse_init is
    begin
      init <= '1';
      tick;
      init <= '0';
    end procedure;

    -- Offer one word until the core takes it (word_ready was 1 at the edge).
    procedure put_word (w : std_logic_vector(31 downto 0)) is
    begin
      word_data  <= w;
      word_valid <= '1';
      loop
        tick;
        exit when word_ready = '1';
      end loop;
      accepted_at := cycle;
      word_valid  <= '0';
    end procedure;

    -- The first n words of block `number` of a padded message.
    procedure put_words (bytes : byte_array; number : natural; n : natural) is
      variable base : natural := number * 64;
    begin
      for i in 0 to n - 1 loop
        put_word(std_logic_vector(to_unsigned(bytes(base + 4 * i), 8)) &
                 std_logic_vector(to_unsigned(bytes(base + 4 * i + 1), 8)) &
                 std_logic_vector(to_unsigned(bytes(base + 4 * i + 2), 8)) &
                 std_logic_vector(to_unsigned(bytes(base + 4 * i + 3), 8)));
      end loop;
    end procedure;

    -- After the 16th word: busy for BLOCK_CYCLES cycles, word_ready low meanwhile, then done.
    procedure await_block is
      variable busy_cycles : natural := 0;
    begin
      loop
        tick;
        exit when busy = '0';
        assert word_ready = '0' report "word_ready is high while the core is busy" severity failure;
        assert done = '0' report "done is high while the core is busy" severity failure;
        busy_cycles := busy_cycles + 1;
      end loop;
      assert busy_cycles = BLOCK_CYCLES
        report "a block lasted " & natural'image(busy_cycles) & " busy cycles, expected " &
               natural'image(BLOCK_CYCLES)
        severity failure;
      assert done = '1' report "done is not set when busy falls" severity failure;
      assert cycle - accepted_at = BLOCK_CYCLES + 1
        report "done came " & natural'image(cycle - accepted_at) & " cycles after the last word"
        severity failure;
    end procedure;

    -- A whole message, starting with init (when `restart`), and its digest.
    procedure hash_message (msg : string; expected : std_logic_vector(255 downto 0);
                            restart : boolean := true) is
      constant bytes  : byte_array := padded(msg);
      constant blocks : natural    := bytes'length / 64;
    begin
      if restart then
        pulse_init;
        tick;  -- the effect of init is visible one edge later
        assert done = '0' report "done survived init" severity failure;
      end if;
      for b in 0 to blocks - 1 loop
        put_words(bytes, b, 16);
        await_block;
      end loop;
      assert digest = expected report "wrong digest for a message of " &
        natural'image(msg'length) & " bytes" severity failure;
    end procedure;
  begin
    -- Reset, then the three FIPS 180-4 vectors of AC-15.1.
    aresetn <= '0';
    tick(3);
    aresetn <= '1';
    tick(2);
    assert word_ready = '1' and busy = '0' and done = '0'
      report "the core is not idle after reset" severity failure;
    assert digest = DIGEST_H0 report "H is not H0 after reset" severity failure;

    hash_message(MSG_ABC, DIGEST_ABC);
    hash_message(MSG_M448, DIGEST_M448);
    hash_message(MSG_M896, DIGEST_M896);

    -- Two messages in sequence, init right after done, in both orders.
    hash_message(MSG_ABC, DIGEST_ABC);
    hash_message(MSG_M896, DIGEST_M896);
    hash_message(MSG_M448, DIGEST_M448);
    hash_message(MSG_ABC, DIGEST_ABC);

    -- The first word of the next block is accepted at once after done: two blocks, no init.
    hash_message(MSG_M448, DIGEST_M448);

    -- Reset in the middle of the load of a block, then a full message.
    pulse_init;
    put_words(padded(MSG_M448), 0, 7);
    aresetn <= '0';
    tick(2);
    aresetn <= '1';
    tick;
    assert word_ready = '1' and busy = '0' and done = '0'
      report "the core is not idle after a reset during the load" severity failure;
    assert digest = DIGEST_H0 report "H is not H0 after a reset during the load" severity failure;
    hash_message(MSG_M448, DIGEST_M448);

    -- Reset during the rounds of the first block of a message, then a full message.
    pulse_init;
    put_words(padded(MSG_M896), 0, 16);
    tick(20);
    assert busy = '1' report "the core is not busy during the rounds" severity failure;
    aresetn <= '0';
    tick(2);
    aresetn <= '1';
    tick;
    assert word_ready = '1' and busy = '0' and done = '0'
      report "the core is not idle after a reset during the rounds" severity failure;
    assert digest = DIGEST_H0 report "H is not H0 after a reset during the rounds" severity failure;
    hash_message(MSG_ABC, DIGEST_ABC);
    hash_message(MSG_M896, DIGEST_M896);

    -- The state after the last digest: idle, done kept until init, H kept.
    tick(5);
    assert done = '1' and busy = '0' and word_ready = '1'
      report "done is not kept after the block" severity failure;
    pulse_init;
    tick;
    assert done = '0' report "done survived init" severity failure;
    assert digest = DIGEST_H0 report "init did not reload H0" severity failure;

    report "SHA256_TB PASSED" severity note;
    finished <= true;
    wait;
  end process;
end architecture sim;
