-- sha256_axi_tb: AXI4-Lite access to the verified padder (T3.20, 1/2, IF-15).
-- Prints "SHA256_AXI_TB PASSED". Working directory: hw/sim/build/xsim-sha-axi.
-- The patterned messages and their digests are sha256_padder_random.txt.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity sha256_axi_tb is
end entity sha256_axi_tb;

architecture sim of sha256_axi_tb is
  constant CLK_PERIOD  : time := 10 ns;
  constant VECTOR_FILE : string := "../../vectors/sha256_padder_random.txt";
  constant DIGEST_EMPTY : std_logic_vector(255 downto 0) :=
    x"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
  constant DIGEST_ABC : std_logic_vector(255 downto 0) :=
    x"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
  constant DIGEST_M448 : std_logic_vector(255 downto 0) :=
    x"248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1";
  constant DIGEST_M896 : std_logic_vector(255 downto 0) :=
    x"cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1";
  constant H0_WORD : std_logic_vector(31 downto 0) := x"6a09e667";

  signal aclk          : std_logic := '0';
  signal aresetn       : std_logic := '0';
  signal s_axi_awaddr  : std_logic_vector(7 downto 0) := (others => '0');
  signal s_axi_awprot  : std_logic_vector(2 downto 0) := (others => '0');
  signal s_axi_awvalid : std_logic := '0';
  signal s_axi_awready : std_logic;
  signal s_axi_wdata   : std_logic_vector(31 downto 0) := (others => '0');
  signal s_axi_wstrb   : std_logic_vector(3 downto 0) := (others => '0');
  signal s_axi_wvalid  : std_logic := '0';
  signal s_axi_wready  : std_logic;
  signal s_axi_bresp   : std_logic_vector(1 downto 0);
  signal s_axi_bvalid  : std_logic;
  signal s_axi_bready  : std_logic := '0';
  signal s_axi_araddr  : std_logic_vector(7 downto 0) := (others => '0');
  signal s_axi_arprot  : std_logic_vector(2 downto 0) := (others => '0');
  signal s_axi_arvalid : std_logic := '0';
  signal s_axi_arready : std_logic;
  signal s_axi_rdata   : std_logic_vector(31 downto 0);
  signal s_axi_rresp   : std_logic_vector(1 downto 0);
  signal s_axi_rvalid  : std_logic;
  signal s_axi_rready  : std_logic := '0';
  signal finished      : boolean := false;

  function pattern_byte(index : natural) return std_logic_vector is
    constant seed : natural := 16#53484132#;
  begin
    return std_logic_vector(to_unsigned((seed + index * 131) mod 256, 8));
  end function;

  function hex_to_slv(text : string(1 to 64)) return std_logic_vector is
    constant HEX : string(1 to 16) := "0123456789abcdef";
    variable nibble : integer;
    variable out_v : std_logic_vector(255 downto 0);
  begin
    for i in 0 to 63 loop
      nibble := -1;
      for h in 1 to 16 loop
        if text(i + 1) = HEX(h) then
          nibble := h - 1;
        end if;
      end loop;
      assert nibble >= 0 report "bad hex digit" severity failure;
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

  dut : entity work.sha256_axi
    port map (
      aclk => aclk, aresetn => aresetn,
      s_axi_awaddr => s_axi_awaddr, s_axi_awprot => s_axi_awprot,
      s_axi_awvalid => s_axi_awvalid, s_axi_awready => s_axi_awready,
      s_axi_wdata => s_axi_wdata, s_axi_wstrb => s_axi_wstrb,
      s_axi_wvalid => s_axi_wvalid, s_axi_wready => s_axi_wready,
      s_axi_bresp => s_axi_bresp, s_axi_bvalid => s_axi_bvalid, s_axi_bready => s_axi_bready,
      s_axi_araddr => s_axi_araddr, s_axi_arprot => s_axi_arprot,
      s_axi_arvalid => s_axi_arvalid, s_axi_arready => s_axi_arready,
      s_axi_rdata => s_axi_rdata, s_axi_rresp => s_axi_rresp,
      s_axi_rvalid => s_axi_rvalid, s_axi_rready => s_axi_rready
    );

  stimulus : process
    procedure tick is
    begin
      wait until rising_edge(aclk);
    end procedure;

    procedure settle is
    begin
      wait for CLK_PERIOD / 4;
    end procedure;

    procedure axi_write(addr : natural; data : std_logic_vector(31 downto 0)) is
      variable guard : natural := 0;
    begin
      s_axi_awaddr <= std_logic_vector(to_unsigned(addr, 8));
      s_axi_awvalid <= '1';
      s_axi_wdata <= data;
      s_axi_wstrb <= "1111";
      s_axi_wvalid <= '1';
      s_axi_bready <= '1';
      loop
        tick;
        exit when s_axi_awready = '1' and s_axi_wready = '1';
        guard := guard + 1;
        assert guard < 200000 report "AXI write stalled" severity failure;
      end loop;
      s_axi_awvalid <= '0';
      s_axi_wvalid <= '0';
      settle;
      assert s_axi_bvalid = '1' and s_axi_bresp = "00" report "write response" severity failure;
      tick;
      settle;
    end procedure;

    procedure axi_read(addr : natural; variable data : out std_logic_vector(31 downto 0)) is
      variable guard : natural := 0;
    begin
      s_axi_araddr <= std_logic_vector(to_unsigned(addr, 8));
      s_axi_arvalid <= '1';
      s_axi_rready <= '1';
      loop
        tick;
        exit when s_axi_arready = '1';
        guard := guard + 1;
        assert guard < 200000 report "AXI read stalled" severity failure;
      end loop;
      s_axi_arvalid <= '0';
      settle;
      assert s_axi_rvalid = '1' and s_axi_rresp = "00" report "read response" severity failure;
      data := s_axi_rdata;
      tick;
      settle;
    end procedure;

    procedure wait_done is
      variable status : std_logic_vector(31 downto 0);
      variable guard : natural := 0;
    begin
      loop
        axi_read(16#04#, status);
        exit when status(2) = '1';
        guard := guard + 1;
        assert guard < 100000 report "DONE timeout" severity failure;
      end loop;
      assert status(1) = '0' report "BUSY stayed high after DONE" severity failure;
    end procedure;

    procedure read_digest(variable got : out std_logic_vector(255 downto 0)) is
      variable word : std_logic_vector(31 downto 0);
    begin
      axi_read(16#10#, word); got(255 downto 224) := word;
      axi_read(16#14#, word); got(223 downto 192) := word;
      axi_read(16#18#, word); got(191 downto 160) := word;
      axi_read(16#1C#, word); got(159 downto 128) := word;
      axi_read(16#20#, word); got(127 downto 96) := word;
      axi_read(16#24#, word); got(95 downto 64) := word;
      axi_read(16#28#, word); got(63 downto 32) := word;
      axi_read(16#2C#, word); got(31 downto 0) := word;
    end procedure;

    procedure put_word(data : std_logic_vector(31 downto 0); nbytes : natural; last : boolean) is
    begin
      if last then
        axi_write(16#0C#, std_logic_vector(to_unsigned(nbytes, 32)));
        axi_write(16#00#, x"00000002");
        if nbytes /= 0 then
          axi_write(16#08#, data);
        end if;
      else
        axi_write(16#08#, data);
      end if;
    end procedure;

    procedure hash_pattern(len : natural; expected : std_logic_vector(255 downto 0)) is
      variable nfull : natural;
      variable nbytes : natural;
      variable base : natural;
      variable word : std_logic_vector(31 downto 0);
      variable got : std_logic_vector(255 downto 0);
      variable b0, b1, b2, b3 : std_logic_vector(7 downto 0);
    begin
      axi_write(16#00#, x"00000001");
      if len = 0 then
        put_word(x"00000000", 0, true);
      else
        if len mod 4 = 0 then
          nfull := len / 4 - 1;
          nbytes := 4;
        else
          nfull := len / 4;
          nbytes := len mod 4;
        end if;
        for w in 0 to nfull - 1 loop
          base := 4 * w;
          word := pattern_byte(base) & pattern_byte(base + 1)
            & pattern_byte(base + 2) & pattern_byte(base + 3);
          put_word(word, 0, false);
        end loop;
        base := 4 * nfull;
        b0 := pattern_byte(base);
        b1 := x"FF"; b2 := x"FF"; b3 := x"FF";
        if nbytes >= 2 then
          b1 := pattern_byte(base + 1);
        end if;
        if nbytes >= 3 then
          b2 := pattern_byte(base + 2);
        end if;
        if nbytes = 4 then
          b3 := pattern_byte(base + 3);
        end if;
        put_word(b0 & b1 & b2 & b3, nbytes, true);
      end if;
      wait_done;
      read_digest(got);
      assert got = expected
        report "AXI digest mismatch for length " & integer'image(len)
        severity failure;
    end procedure;

    procedure hash_bytes(text : string; expected : std_logic_vector(255 downto 0)) is
      variable len : natural := text'length;
      variable nfull : natural;
      variable nbytes : natural;
      variable base : natural;
      variable word : std_logic_vector(31 downto 0);
      variable got : std_logic_vector(255 downto 0);
      variable raw : std_logic_vector(7 downto 0);
    begin
      axi_write(16#00#, x"00000001");
      if len = 0 then
        put_word(x"00000000", 0, true);
      else
        if len mod 4 = 0 then
          nfull := len / 4 - 1;
          nbytes := 4;
        else
          nfull := len / 4;
          nbytes := len mod 4;
        end if;
        for w in 0 to nfull - 1 loop
          base := 4 * w;
          word := std_logic_vector(to_unsigned(character'pos(text(text'left + base)), 8))
            & std_logic_vector(to_unsigned(character'pos(text(text'left + base + 1)), 8))
            & std_logic_vector(to_unsigned(character'pos(text(text'left + base + 2)), 8))
            & std_logic_vector(to_unsigned(character'pos(text(text'left + base + 3)), 8));
          put_word(word, 0, false);
        end loop;
        base := 4 * nfull;
        word := (others => '1');
        for b in 0 to nbytes - 1 loop
          raw := std_logic_vector(to_unsigned(character'pos(text(text'left + base + b)), 8));
          word(31 - 8 * b downto 24 - 8 * b) := raw;
        end loop;
        put_word(word, nbytes, true);
      end if;
      wait_done;
      read_digest(got);
      assert got = expected report "AXI string digest mismatch" severity failure;
    end procedure;

    procedure apply_reset is
    begin
      s_axi_awvalid <= '0';
      s_axi_wvalid <= '0';
      s_axi_arvalid <= '0';
      aresetn <= '0';
      tick;
      settle;
      tick;
      settle;
      aresetn <= '1';
      settle;
    end procedure;

    variable word : std_logic_vector(31 downto 0);
    variable before_digest : std_logic_vector(31 downto 0);
    file vecs : text open read_mode is VECTOR_FILE;
    variable row : line;
    variable len_v : integer;
    variable hexdig : string(1 to 64);
    variable ch : character;
    variable good : boolean;
    variable count : natural := 0;
    variable saw55, saw56, saw63, saw64, saw119, saw120 : boolean := false;
  begin
    apply_reset;
    axi_read(16#30#, word);
    assert word = x"00000000" report "VERSION reset value" severity failure;
    axi_read(16#10#, word);
    assert word = H0_WORD report "DIGEST0 is not H0 after reset" severity failure;
    axi_read(16#04#, word);
    assert word(2) = '0' and word(1) = '0' report "STATUS not idle after reset" severity failure;
    before_digest := word;
    axi_write(16#10#, x"ffffffff");
    axi_write(16#30#, x"ffffffff");
    axi_write(16#04#, x"ffffffff");
    axi_read(16#10#, word);
    assert word = H0_WORD report "a write to DIGEST changed it" severity failure;
    axi_read(16#30#, word);
    assert word = x"00000000" report "a write to VERSION changed it" severity failure;
    axi_read(16#00#, word);
    assert word = x"00000000" report "CTRL reads back as nonzero" severity failure;

    hash_bytes("", DIGEST_EMPTY);
    hash_bytes("abc", DIGEST_ABC);
    hash_bytes("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", DIGEST_M448);
    hash_bytes(
      "abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu",
      DIGEST_M896);

    apply_reset;
    hash_bytes("abc", DIGEST_ABC);
    hash_bytes("", DIGEST_EMPTY);

    while not endfile(vecs) loop
      readline(vecs, row);
      if row = null or row.all'length = 0 or row.all(row.all'left) = '#' then
        next;
      end if;
      read(row, len_v, good);
      assert good report "vector length" severity failure;
      loop
        read(row, ch, good);
        exit when not good or ch /= ' ';
      end loop;
      hexdig(1) := ch;
      for i in 2 to 64 loop
        read(row, ch, good);
        assert good report "short digest" severity failure;
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
    end loop;
    assert count >= 1000 report "fewer than 1000 AXI vectors" severity failure;
    assert saw55 and saw56 and saw63 and saw64 and saw119 and saw120
      report "a boundary length is missing" severity failure;
    report "sha axi vectors: " & integer'image(count);
    report "SHA256_AXI_TB PASSED";
    finished <= true;
    wait;
  end process;
end architecture sim;
