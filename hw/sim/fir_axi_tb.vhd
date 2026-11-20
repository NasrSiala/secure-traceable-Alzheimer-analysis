-- fir_axi_tb: AXI4-Lite access to fir_decim (T3.20, 2/2, IF-16).
-- Extremes from l14, then the 20 signals of fir_decim_random.txt.
-- Reading DATA_OUT consumes the sample. Prints "FIR_AXI_TB PASSED".
-- Working directory: hw/sim/build/xsim-fir-axi.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity fir_axi_tb is
end entity fir_axi_tb;

architecture sim of fir_axi_tb is
  constant CLK_PERIOD : time := 10 ns;
  constant VECTOR_FILE : string := "../../vectors/fir_decim_random.txt";
  constant COEF : std_logic_vector(31 downto 0) := x"ca0e824c";

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

  dut : entity work.fir_axi
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
        assert guard < 400000 report "FIR AXI write stalled" severity failure;
      end loop;
      s_axi_awvalid <= '0';
      s_axi_wvalid <= '0';
      settle;
      assert s_axi_bvalid = '1' and s_axi_bresp = "00" report "FIR write response" severity failure;
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
        assert guard < 400000 report "FIR AXI read stalled" severity failure;
      end loop;
      s_axi_arvalid <= '0';
      settle;
      assert s_axi_rvalid = '1' and s_axi_rresp = "00" report "FIR read response" severity failure;
      data := s_axi_rdata;
      tick;
      settle;
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

    procedure push(sample : integer; produces : boolean; check : boolean; expected : integer) is
      variable wide : std_logic_vector(31 downto 0);
      variable got : integer;
      variable guard : natural := 0;
    begin
      wide := std_logic_vector(resize(to_signed(sample, 16), 32));
      axi_write(16#08#, wide);
      if produces then
        loop
          axi_read(16#04#, wide);
          exit when wide(1) = '1';
          guard := guard + 1;
          assert guard < 400 report "OUT_VALID timeout" severity failure;
        end loop;
        assert wide(0) = '0' report "IN_READY high while an output is pending" severity failure;
        axi_read(16#0C#, wide);
        got := to_integer(signed(wide(15 downto 0)));
        if check then
          assert got = expected
            report "AXI FIR mismatch, got " & integer'image(got)
            severity failure;
        end if;
        axi_read(16#04#, wide);
        assert wide(1) = '0' report "DATA_OUT read did not consume the sample" severity failure;
      end if;
    end procedure;

    variable word : std_logic_vector(31 downto 0);
    file vecs : text open read_mode is VECTOR_FILE;
    variable row : line;
    variable ok : boolean;
    variable signal_count : integer;
    variable input_length : integer;
    variable id_text : string(1 to 8);
    variable sample : integer;
    variable expected : integer;
    variable outputs : natural;
  begin
    apply_reset;
    axi_read(16#14#, word);
    assert word = x"00000000" report "FIR VERSION" severity failure;
    axi_read(16#10#, word);
    assert word = COEF report "FIR COEF_ID" severity failure;
    axi_write(16#10#, x"ffffffff");
    axi_write(16#14#, x"ffffffff");
    axi_write(16#0C#, x"ffffffff");
    axi_read(16#10#, word);
    assert word = COEF report "a write to COEF_ID changed it" severity failure;
    axi_read(16#14#, word);
    assert word = x"00000000" report "a write to FIR VERSION changed it" severity failure;

    -- The constant runs check the rails inside push only for the file.
    -- Here the direct extremes bench owns the full expected list. This run
    -- checks that CLEAR lets a second derivation start, and that +32767 and
    -- -32768 both produce a saturated sample (the 13th output, index 12).
    axi_write(16#00#, x"00000001");
    for index in 0 to 110 loop
      if index = 60 then
        push(32767, true, true, 32767);
      elsif index mod 5 = 0 then
        push(32767, true, false, 0);
      else
        push(32767, false, false, 0);
      end if;
    end loop;
    axi_write(16#00#, x"00000001");
    for index in 0 to 110 loop
      if index = 60 then
        push(-32768, true, true, -32768);
      elsif index mod 5 = 0 then
        push(-32768, true, false, 0);
      else
        push(-32768, false, false, 0);
      end if;
    end loop;

    -- Header, then the 20 signals of the direct-core vector file.
    readline(vecs, row);
    while row /= null and (row.all'length = 0 or row.all(row.all'left) = '#') loop
      readline(vecs, row);
    end loop;
    read(row, signal_count, ok);
    readline(vecs, row);
    read(row, input_length, ok);
    readline(vecs, row);
    id_text := row.all(row.all'left to row.all'left + 7);
    assert id_text = "ca0e824c" report "vector coef id" severity failure;
    assert signal_count = 20 and input_length = 5055 report "vector shape" severity failure;

    for s in 0 to signal_count - 1 loop
      axi_write(16#00#, x"00000001");
      outputs := 0;
      for index in 0 to input_length - 1 loop
        readline(vecs, row);
        read(row, sample, ok);
        if index mod 5 = 0 then
          readline(vecs, row);
          read(row, expected, ok);
          push(sample, true, true, expected);
          outputs := outputs + 1;
        else
          push(sample, false, false, 0);
        end if;
      end loop;
      assert outputs = 1011 report "AXI signal output count" severity failure;
    end loop;

    report "FIR_AXI_TB PASSED";
    finished <= true;
    wait;
  end process;
end architecture sim;
