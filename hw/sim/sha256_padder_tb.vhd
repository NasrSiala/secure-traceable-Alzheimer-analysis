-- sha256_padder_tb: self-checking VHDL-2008 testbench of sha256_padder (T3.18, 2/2).
--
-- Run it in Vivado xsim (`make -C hw/sim xsim-padder`, and the default target when GHDL and
-- cocotb are not installed). It prints "SHA256_PADDER_TB PASSED" and stops at the first failure.
-- The oracle for the literals below is hashlib, checked by tests/scripts/test_sha256_padder.py.
-- Patterned messages (byte[i] = (16#53484132# + i*131) mod 256) and their digests are the shared
-- file sha256_padder_random.txt, also checked against hashlib by that test. The bench is started
-- with its working directory in hw/sim/build/xsim-padder, so the file path is relative to there.
--
-- What it checks:
--   - the empty message and "abc" (AC-15.1), with 0xFF in the ignored low bytes of a short word;
--   - the FIPS 448-bit and 896-bit messages (AC-15.1), so multi-block chaining goes through the padder;
--   - every patterned vector in the file: the boundary lengths 55, 56, 63, 64, 119 and 120
--     (AC-15.2), one length for each final-word byte count, and 1000 lengths from the fixed seed;
--   - two messages in a row; done held until init; reset during the beats and during the rounds.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity sha256_padder_tb is
end entity sha256_padder_tb;

architecture sim of sha256_padder_tb is
  constant CLK_PERIOD  : time := 10 ns;
  constant VECTOR_FILE : string := "../../vectors/sha256_padder_random.txt";
  constant CYCLE_LIMIT : natural := 20000;

  constant DIGEST_EMPTY : std_logic_vector(255 downto 0) :=
    x"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
  constant DIGEST_ABC : std_logic_vector(255 downto 0) :=
    x"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
  constant DIGEST_M448 : std_logic_vector(255 downto 0) :=
    x"248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1";
  constant DIGEST_M896 : std_logic_vector(255 downto 0) :=
    x"cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1";
  constant DIGEST_H0 : std_logic_vector(255 downto 0) :=
    x"6a09e667bb67ae853c6ef372a54ff53a510e527f9b05688c1f83d9ab5be0cd19";

  constant MSG_ABC  : string := "abc";
  constant MSG_M448 : string := "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
  constant MSG_M896 : string :=
    "abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu";

  type byte_array is array (natural range <>) of natural range 0 to 255;

  signal aclk     : std_logic := '0';
  signal aresetn  : std_logic := '0';
  signal init     : std_logic := '0';
  signal in_valid : std_logic := '0';
  signal in_ready : std_logic;
  signal in_data  : std_logic_vector(31 downto 0) := (others => '0');
  signal in_last  : std_logic := '0';
  signal in_bytes : std_logic_vector(2 downto 0) := (others => '0');
  signal busy     : std_logic;
  signal done     : std_logic;
  signal digest   : std_logic_vector(255 downto 0);

  signal finished : boolean := false;

  function pattern_byte(index : natural) return std_logic_vector is
    constant seed : natural := 16#53484132#;
  begin
    return std_logic_vector(to_unsigned((seed + index * 131) mod 256, 8));
  end function;

  function to_hex(value : std_logic_vector(255 downto 0)) return string is
    constant HEX : string(1 to 16) := "0123456789abcdef";
    variable text : string(1 to 64);
    variable nibble : natural;
  begin
    for i in 0 to 63 loop
      nibble := to_integer(unsigned(value(255 - 4 * i downto 252 - 4 * i)));
      text(i + 1) := HEX(nibble + 1);
    end loop;
    return text;
  end function;

  function hex_to_slv(text : string(1 to 64)) return std_logic_vector is
    variable out_v : std_logic_vector(255 downto 0) := (others => '0');
    variable nibble : integer;
    variable c : character;
  begin
    for i in 0 to 63 loop
      c := text(i + 1);
      if c >= '0' and c <= '9' then
        nibble := character'pos(c) - character'pos('0');
      elsif c >= 'a' and c <= 'f' then
        nibble := character'pos(c) - character'pos('a') + 10;
      elsif c >= 'A' and c <= 'F' then
        nibble := character'pos(c) - character'pos('A') + 10;
      else
        nibble := -1;
      end if;
      assert nibble >= 0 report "bad hex digit in the vector file" severity failure;
      out_v(255 - 4 * i downto 252 - 4 * i) := std_logic_vector(to_unsigned(nibble, 4));
    end loop;
    return out_v;
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

  dut : entity work.sha256_padder
    port map (
      aclk      => aclk,
      aresetn   => aresetn,
      init      => init,
      in_valid  => in_valid,
      in_ready  => in_ready,
      in_data   => in_data,
      in_last   => in_last,
      in_bytes  => in_bytes,
      busy      => busy,
      done      => done,
      digest    => digest
    );

  stimulus : process
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
      tick;
      assert done = '0' report "done survived init" severity failure;
      assert busy = '1' report "a message is not busy after init" severity failure;
      assert in_ready = '1' report "the padder does not accept a beat after init" severity failure;
    end procedure;

    -- in_bytes is applied only with in_last. Non-final beats are offered with a count of 0.
    procedure put_beat(word : std_logic_vector(31 downto 0); nbytes : natural; last : boolean) is
      variable guard : natural := 0;
    begin
      in_data  <= word;
      in_bytes <= std_logic_vector(to_unsigned(nbytes, 3));
      if last then
        in_last <= '1';
      else
        in_last <= '0';
      end if;
      in_valid <= '1';
      loop
        tick;
        exit when in_ready = '1';
        guard := guard + 1;
        assert guard < CYCLE_LIMIT report "in_ready stayed low" severity failure;
      end loop;
      in_valid <= '0';
      in_last  <= '0';
    end procedure;

    procedure await_done is
      variable guard : natural := 0;
    begin
      loop
        tick;
        exit when done = '1';
        guard := guard + 1;
        assert guard < CYCLE_LIMIT report "timeout waiting for done" severity failure;
      end loop;
      assert busy = '0' report "busy stayed high after done" severity failure;
    end procedure;

    procedure check_digest(expected : std_logic_vector(255 downto 0); what : string) is
    begin
      assert digest = expected
        report "wrong digest for " & what & ", got " & to_hex(digest)
        severity failure;
    end procedure;

    procedure send_bytes(len : natural; bytes : byte_array) is
      variable nfull  : natural;
      variable nbytes : natural;
      variable base   : natural;
      variable b0, b1, b2, b3 : std_logic_vector(7 downto 0);
    begin
      if len = 0 then
        put_beat(x"FFFFFFFF", 0, true);
        return;
      end if;
      if len mod 4 = 0 then
        nfull  := len / 4 - 1;
        nbytes := 4;
      else
        nfull  := len / 4;
        nbytes := len mod 4;
      end if;
      for w in 0 to nfull - 1 loop
        base := 4 * w;
        b0 := std_logic_vector(to_unsigned(bytes(base), 8));
        b1 := std_logic_vector(to_unsigned(bytes(base + 1), 8));
        b2 := std_logic_vector(to_unsigned(bytes(base + 2), 8));
        b3 := std_logic_vector(to_unsigned(bytes(base + 3), 8));
        put_beat(b0 & b1 & b2 & b3, 0, false);
      end loop;
      base := 4 * nfull;
      b0 := std_logic_vector(to_unsigned(bytes(base), 8));
      if nbytes = 4 then
        b1 := std_logic_vector(to_unsigned(bytes(base + 1), 8));
        b2 := std_logic_vector(to_unsigned(bytes(base + 2), 8));
        b3 := std_logic_vector(to_unsigned(bytes(base + 3), 8));
      elsif nbytes = 3 then
        b1 := std_logic_vector(to_unsigned(bytes(base + 1), 8));
        b2 := std_logic_vector(to_unsigned(bytes(base + 2), 8));
        b3 := x"FF";
      elsif nbytes = 2 then
        b1 := std_logic_vector(to_unsigned(bytes(base + 1), 8));
        b2 := x"FF";
        b3 := x"FF";
      else
        b1 := x"FF";
        b2 := x"FF";
        b3 := x"FF";
      end if;
      put_beat(b0 & b1 & b2 & b3, nbytes, true);
    end procedure;

    procedure send_string(msg : string) is
      variable bytes : byte_array(0 to 127) := (others => 0);
      variable k : natural := 0;
    begin
      assert msg'length <= 128 report "raw message longer than the bench buffer" severity failure;
      for i in msg'range loop
        bytes(k) := character'pos(msg(i));
        k := k + 1;
      end loop;
      send_bytes(msg'length, bytes);
    end procedure;

    procedure send_pattern(len : natural) is
      variable bytes : byte_array(0 to 4096) := (others => 0);
    begin
      assert len <= 4096 report "pattern longer than 4096 bytes" severity failure;
      for i in 0 to len - 1 loop
        bytes(i) := to_integer(unsigned(pattern_byte(i)));
      end loop;
      send_bytes(len, bytes);
    end procedure;

    procedure hash_string(msg : string; expected : std_logic_vector(255 downto 0)) is
    begin
      pulse_init;
      send_string(msg);
      await_done;
      check_digest(expected, "a raw message of " & integer'image(msg'length) & " bytes");
    end procedure;

    procedure hash_pattern(len : natural; expected : std_logic_vector(255 downto 0)) is
    begin
      pulse_init;
      send_pattern(len);
      await_done;
      check_digest(expected, "a patterned message of " & integer'image(len) & " bytes");
    end procedure;

    procedure hash_vector_file is
      file vecs : text open read_mode is VECTOR_FILE;
      variable row : line;
      variable len_v : integer;
      variable hexdig : string(1 to 64);
      variable ch : character;
      variable good : boolean;
      variable count : natural := 0;
      variable saw55, saw56, saw63, saw64, saw119, saw120 : boolean := false;
    begin
      while not endfile(vecs) loop
        readline(vecs, row);
        if row = null or row.all'length = 0 then
          next;
        end if;
        if row.all(row.all'left) = '#' then
          next;
        end if;
        read(row, len_v, good);
        assert good report "a vector line has no length" severity failure;
        assert len_v >= 0 and len_v <= 4096
          report "a vector length is outside 0 to 4096" severity failure;
        loop
          read(row, ch, good);
          exit when not good or ch /= ' ';
        end loop;
        assert good report "a vector line has no digest" severity failure;
        hexdig(1) := ch;
        for i in 2 to 64 loop
          read(row, ch, good);
          assert good report "a digest is shorter than 64 digits" severity failure;
          hexdig(i) := ch;
        end loop;
        hash_pattern(len_v, hex_to_slv(hexdig));
        count := count + 1;
        if len_v = 55 then saw55 := true; end if;
        if len_v = 56 then saw56 := true; end if;
        if len_v = 63 then saw63 := true; end if;
        if len_v = 64 then saw64 := true; end if;
        if len_v = 119 then saw119 := true; end if;
        if len_v = 120 then saw120 := true; end if;
        if count mod 100 = 0 then
          report "padder vectors so far: " & integer'image(count) severity note;
        end if;
      end loop;
      assert count >= 1000
        report "the vector file has " & integer'image(count) & " messages, expected at least 1000"
        severity failure;
      assert saw55 and saw56 and saw63 and saw64 and saw119 and saw120
        report "a boundary length is missing from the vector file" severity failure;
      report "padder vectors: " & integer'image(count) severity note;
    end procedure;

    procedure apply_reset is
    begin
      in_valid <= '0';
      in_last  <= '0';
      init     <= '0';
      aresetn  <= '0';
      tick(2);
      aresetn  <= '1';
      tick(2);
      assert busy = '0' and done = '0'
        report "the padder is not idle after reset" severity failure;
      assert digest = DIGEST_H0 report "H is not H0 after reset" severity failure;
      assert in_ready = '0' report "a beat was accepted before init" severity failure;
    end procedure;
  begin
    apply_reset;

    hash_string("", DIGEST_EMPTY);
    hash_string(MSG_ABC, DIGEST_ABC);
    hash_string(MSG_M448, DIGEST_M448);
    hash_string(MSG_M896, DIGEST_M896);

    -- Reuse, both orders, with no reset.
    hash_string(MSG_ABC, DIGEST_ABC);
    hash_string("", DIGEST_EMPTY);
    hash_string(MSG_M896, DIGEST_M896);
    hash_string(MSG_M448, DIGEST_M448);

    hash_vector_file;

    -- Reset after the last beat of a 12-byte message, while the padding is still in flight.
    pulse_init;
    send_pattern(12);
    apply_reset;
    hash_string(MSG_ABC, DIGEST_ABC);

    -- Reset while the core is in its rounds: 16 words fill a block, then the padder waits.
    pulse_init;
    for w in 0 to 15 loop
      put_beat(pattern_byte(4 * w) & pattern_byte(4 * w + 1) &
               pattern_byte(4 * w + 2) & pattern_byte(4 * w + 3), 0, false);
    end loop;
    tick(8);
    assert busy = '1' report "the padder went idle during a block" severity failure;
    apply_reset;
    hash_string("", DIGEST_EMPTY);
    hash_string(MSG_M896, DIGEST_M896);

    tick(4);
    assert done = '1' and busy = '0' report "done is not kept after the message" severity failure;
    pulse_init;
    assert done = '0' report "done survived init" severity failure;

    report "SHA256_PADDER_TB PASSED" severity note;
    finished <= true;
    wait;
  end process;
end architecture sim;
