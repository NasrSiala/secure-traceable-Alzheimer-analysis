-- Audit round 9: protocol test bench for hw/rtl/axil_reg_bringup.vhd (T1.9).
--
-- Not part of the project (the register is a bring-up spike that T3.20 replaces): it shows, with
-- the Vivado simulator, that the register behaves as an AXI4-Lite slave and as hw/BRINGUP.md says.
-- Run it with run_xsim.py. It ends with the line "ALL TESTS PASSED"; any failed check stops the
-- run with a message that names the check.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_axil_reg_bringup is
end entity tb_axil_reg_bringup;

architecture sim of tb_axil_reg_bringup is
  signal aclk          : std_logic := '0';
  signal aresetn       : std_logic := '0';
  signal s_axi_awaddr  : std_logic_vector(3 downto 0)  := (others => '0');
  signal s_axi_awprot  : std_logic_vector(2 downto 0)  := (others => '0');
  signal s_axi_awvalid : std_logic := '0';
  signal s_axi_awready : std_logic;
  signal s_axi_wdata   : std_logic_vector(31 downto 0) := (others => '0');
  signal s_axi_wstrb   : std_logic_vector(3 downto 0)  := (others => '0');
  signal s_axi_wvalid  : std_logic := '0';
  signal s_axi_wready  : std_logic;
  signal s_axi_bresp   : std_logic_vector(1 downto 0);
  signal s_axi_bvalid  : std_logic;
  signal s_axi_bready  : std_logic := '0';
  signal s_axi_araddr  : std_logic_vector(3 downto 0)  := (others => '0');
  signal s_axi_arprot  : std_logic_vector(2 downto 0)  := (others => '0');
  signal s_axi_arvalid : std_logic := '0';
  signal s_axi_arready : std_logic;
  signal s_axi_rdata   : std_logic_vector(31 downto 0);
  signal s_axi_rresp   : std_logic_vector(1 downto 0);
  signal s_axi_rvalid  : std_logic;
  signal s_axi_rready  : std_logic := '0';
  signal finished      : boolean := false;
begin
  aclk <= not aclk after 5 ns when not finished else aclk;

  dut : entity work.axil_reg_bringup
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
      s_axi_rvalid => s_axi_rvalid, s_axi_rready => s_axi_rready);

  stimulus : process
    -- Inputs change 1 ns after a rising edge; the outputs are read at the edge, which gives the
    -- values the design sees on that edge.
    procedure edge_then_settle is
    begin
      wait until rising_edge(aclk);
      wait for 1 ns;
    end procedure;

    procedure idle (cycles : natural) is
    begin
      for i in 1 to cycles loop
        edge_then_settle;
      end loop;
    end procedure;

    -- A write whose address and data arrive aw_delay and w_delay cycles after the start; the
    -- response is accepted b_delay cycles after bvalid rose. Checks the handshake rules on the way.
    procedure axi_write (
      addr     : std_logic_vector(3 downto 0);
      data     : std_logic_vector(31 downto 0);
      strb     : std_logic_vector(3 downto 0);
      aw_delay : natural := 0;
      w_delay  : natural := 0;
      b_delay  : natural := 0) is
      variable aw_done : boolean := false;
      variable w_done  : boolean := false;
      variable waited  : natural := 0;
    begin
      for cycle in 0 to 60 loop
        if cycle >= aw_delay and not aw_done then
          s_axi_awvalid <= '1'; s_axi_awaddr <= addr;
        end if;
        if cycle >= w_delay and not w_done then
          s_axi_wvalid <= '1'; s_axi_wdata <= data; s_axi_wstrb <= strb;
        end if;
        wait until rising_edge(aclk);
        -- Neither channel may be accepted while the other one is not offered.
        if s_axi_awvalid = '1' and s_axi_awready = '1' then
          assert s_axi_wvalid = '1' report "CHECK write: address accepted before the data was offered" severity failure;
          aw_done := true;
        end if;
        if s_axi_wvalid = '1' and s_axi_wready = '1' then
          assert s_axi_awvalid = '1' report "CHECK write: data accepted before the address was offered" severity failure;
          w_done := true;
        end if;
        assert (s_axi_awready = '1') = (s_axi_wready = '1')
          report "CHECK write: the address and the data are not accepted together" severity failure;
        wait for 1 ns;
        if aw_done then s_axi_awvalid <= '0'; end if;
        if w_done  then s_axi_wvalid  <= '0'; end if;
        exit when aw_done and w_done;
      end loop;
      assert aw_done and w_done report "CHECK write: the write was never accepted" severity failure;
      -- The response: bvalid within two cycles, held until bready, OKAY.
      while s_axi_bvalid /= '1' loop
        edge_then_settle;
        waited := waited + 1;
        assert waited <= 3 report "CHECK write: no response" severity failure;
      end loop;
      for i in 1 to b_delay loop
        assert s_axi_bvalid = '1' report "CHECK write: bvalid dropped before bready" severity failure;
        assert s_axi_bresp = "00" report "CHECK write: bresp is not OKAY" severity failure;
        assert s_axi_awready = '0' and s_axi_wready = '0'
          report "CHECK write: a second write was accepted while the response is pending" severity failure;
        edge_then_settle;
      end loop;
      s_axi_bready <= '1';
      wait until rising_edge(aclk);
      assert s_axi_bvalid = '1' and s_axi_bresp = "00" report "CHECK write: no OKAY at the handshake" severity failure;
      wait for 1 ns;
      s_axi_bready <= '0';
      assert s_axi_bvalid = '0' report "CHECK write: bvalid stayed up after the handshake" severity failure;
    end procedure;

    -- A read; rdata is returned through the out parameter. The data is accepted r_delay cycles after
    -- rvalid rose; it must not move while it waits.
    procedure axi_read (
      addr    : std_logic_vector(3 downto 0);
      data    : out std_logic_vector(31 downto 0);
      r_delay : natural := 0) is
      variable waited : natural := 0;
      variable seen   : std_logic_vector(31 downto 0);
    begin
      s_axi_arvalid <= '1'; s_axi_araddr <= addr;
      wait until rising_edge(aclk);
      assert s_axi_arready = '1' report "CHECK read: the address was not accepted" severity failure;
      wait for 1 ns;
      s_axi_arvalid <= '0';
      while s_axi_rvalid /= '1' loop
        edge_then_settle;
        waited := waited + 1;
        assert waited <= 3 report "CHECK read: no data" severity failure;
      end loop;
      seen := s_axi_rdata;
      for i in 1 to r_delay loop
        assert s_axi_rvalid = '1' report "CHECK read: rvalid dropped before rready" severity failure;
        assert s_axi_rdata = seen report "CHECK read: rdata moved while it waited" severity failure;
        assert s_axi_rresp = "00" report "CHECK read: rresp is not OKAY" severity failure;
        assert s_axi_arready = '0' report "CHECK read: a second read was accepted while the data waits" severity failure;
        edge_then_settle;
      end loop;
      s_axi_rready <= '1';
      wait until rising_edge(aclk);
      assert s_axi_rvalid = '1' and s_axi_rresp = "00" report "CHECK read: no OKAY at the handshake" severity failure;
      data := s_axi_rdata;
      wait for 1 ns;
      s_axi_rready <= '0';
      assert s_axi_rvalid = '0' report "CHECK read: rvalid stayed up after the handshake" severity failure;
    end procedure;

    variable got : std_logic_vector(31 downto 0);
  begin
    -- Reset: nothing offered by the slave.
    aresetn <= '0';
    idle(4);
    assert s_axi_bvalid = '0' and s_axi_rvalid = '0' report "CHECK reset: a response is offered" severity failure;
    assert s_axi_awready = '0' and s_axi_wready = '0' and s_axi_arready = '0'
      report "CHECK reset: ready is up with nothing offered" severity failure;
    aresetn <= '1';
    idle(2);

    -- The register resets to 0.
    axi_read(x"0", got);
    assert got = x"00000000" report "CHECK reset value is not 0" severity failure;

    -- Write, then read back: all patterns of the host test.
    for i in 0 to 5 loop
      case i is
        when 0 => axi_write(x"0", x"DEADBEEF", "1111");
        when 1 => axi_write(x"0", x"00000000", "1111");
        when 2 => axi_write(x"0", x"A5A5A5A5", "1111");
        when 3 => axi_write(x"0", x"5A5A5A5A", "1111");
        when 4 => axi_write(x"0", x"FFFFFFFF", "1111");
        when others => axi_write(x"0", x"00000001", "1111");
      end case;
      axi_read(x"0", got);
      case i is
        when 0 => assert got = x"DEADBEEF" report "CHECK readback 0xDEADBEEF" severity failure;
        when 1 => assert got = x"00000000" report "CHECK readback 0" severity failure;
        when 2 => assert got = x"A5A5A5A5" report "CHECK readback 0xA5A5A5A5" severity failure;
        when 3 => assert got = x"5A5A5A5A" report "CHECK readback 0x5A5A5A5A" severity failure;
        when 4 => assert got = x"FFFFFFFF" report "CHECK readback 0xFFFFFFFF" severity failure;
        when others => assert got = x"00000001" report "CHECK readback 1" severity failure;
      end case;
    end loop;

    -- Byte strobes: only the strobed bytes change.
    axi_write(x"0", x"11223344", "1111");
    axi_write(x"0", x"AABBCCDD", "0101");
    axi_read(x"0", got);
    assert got = x"11BB33DD" report "CHECK strobes 0101 on 0x11223344" severity failure;
    axi_write(x"0", x"FFFFFFFF", "0000");
    axi_read(x"0", got);
    assert got = x"11BB33DD" report "CHECK a write with no strobe changed the register" severity failure;

    -- The response and the data are held until the master takes them.
    axi_write(x"0", x"CAFEBABE", "1111", b_delay => 4);
    axi_read(x"0", got, r_delay => 4);
    assert got = x"CAFEBABE" report "CHECK write and read with a slow master" severity failure;

    -- The address and the data arrive at different times, in both orders.
    axi_write(x"0", x"01020304", "1111", aw_delay => 0, w_delay => 5);
    axi_read(x"0", got);
    assert got = x"01020304" report "CHECK address first, data later" severity failure;
    axi_write(x"0", x"05060708", "1111", aw_delay => 5, w_delay => 0);
    axi_read(x"0", got);
    assert got = x"05060708" report "CHECK data first, address later" severity failure;

    -- An address alone does not write and does not get a response.
    s_axi_awvalid <= '1'; s_axi_awaddr <= x"0";
    idle(6);
    assert s_axi_awready = '0' and s_axi_bvalid = '0'
      report "CHECK an address without data was accepted" severity failure;
    s_axi_awvalid <= '0';
    idle(1);
    axi_read(x"0", got);
    assert got = x"05060708" report "CHECK an address alone changed the register" severity failure;

    -- Other word addresses: writes ignored (but answered), reads return 0.
    axi_write(x"4", x"FFFFFFFF", "1111");
    axi_write(x"8", x"FFFFFFFF", "1111");
    axi_write(x"C", x"FFFFFFFF", "1111");
    axi_read(x"0", got);
    assert got = x"05060708" report "CHECK a write at 0x4, 0x8 or 0xC changed the register" severity failure;
    axi_read(x"4", got);
    assert got = x"00000000" report "CHECK a read at 0x4 is not 0" severity failure;
    axi_read(x"C", got);
    assert got = x"00000000" report "CHECK a read at 0xC is not 0" severity failure;

    -- A read and a write offered on the same edge are both served.
    s_axi_arvalid <= '1'; s_axi_araddr <= x"0";
    s_axi_awvalid <= '1'; s_axi_awaddr <= x"0";
    s_axi_wvalid  <= '1'; s_axi_wdata <= x"0BADF00D"; s_axi_wstrb <= "1111";
    wait until rising_edge(aclk);
    assert s_axi_arready = '1' and s_axi_awready = '1' and s_axi_wready = '1'
      report "CHECK a read and a write on the same edge were not both accepted" severity failure;
    wait for 1 ns;
    s_axi_arvalid <= '0'; s_axi_awvalid <= '0'; s_axi_wvalid <= '0';
    s_axi_bready <= '1'; s_axi_rready <= '1';
    idle(3);
    s_axi_bready <= '0'; s_axi_rready <= '0';
    axi_read(x"0", got);
    assert got = x"0BADF00D" report "CHECK simultaneous write lost" severity failure;

    -- A second write offered while the first response is pending is held back, not lost.
    s_axi_awvalid <= '1'; s_axi_awaddr <= x"0";
    s_axi_wvalid  <= '1'; s_axi_wdata <= x"1111AAAA"; s_axi_wstrb <= "1111";
    wait until rising_edge(aclk);
    wait for 1 ns;
    s_axi_awvalid <= '0'; s_axi_wvalid <= '0';
    assert s_axi_bvalid = '1' report "CHECK pending: no response for the first write" severity failure;
    s_axi_awvalid <= '1'; s_axi_wvalid <= '1'; s_axi_wdata <= x"2222BBBB";
    for i in 1 to 4 loop
      wait until rising_edge(aclk);
      assert s_axi_awready = '0' and s_axi_wready = '0'
        report "CHECK pending: a second write was accepted while the response is pending" severity failure;
      assert s_axi_bvalid = '1' report "CHECK pending: bvalid dropped" severity failure;
      wait for 1 ns;
    end loop;
    axi_read(x"0", got);
    assert got = x"1111AAAA" report "CHECK pending: the held-back write already changed the register" severity failure;
    s_axi_bready <= '1';
    wait until rising_edge(aclk);
    wait for 1 ns;
    s_axi_bready <= '0';
    wait until rising_edge(aclk);
    assert s_axi_awready = '1' and s_axi_wready = '1'
      report "CHECK pending: the held-back write was not taken once the response was accepted" severity failure;
    wait for 1 ns;
    s_axi_awvalid <= '0'; s_axi_wvalid <= '0';
    s_axi_bready <= '1';
    idle(2);
    s_axi_bready <= '0';
    axi_read(x"0", got);
    assert got = x"2222BBBB" report "CHECK pending: the held-back write was lost" severity failure;

    -- A second read offered while the first data waits is held back.
    s_axi_arvalid <= '1'; s_axi_araddr <= x"0";
    wait until rising_edge(aclk);
    wait for 1 ns;
    assert s_axi_rvalid = '1' report "CHECK pending read: no data" severity failure;
    for i in 1 to 3 loop
      wait until rising_edge(aclk);
      assert s_axi_arready = '0' report "CHECK pending read: a second read was accepted while the data waits" severity failure;
      assert s_axi_rvalid = '1' and s_axi_rdata = x"2222BBBB" report "CHECK pending read: the data moved" severity failure;
      wait for 1 ns;
    end loop;
    s_axi_rready <= '1';
    wait until rising_edge(aclk);
    wait for 1 ns;
    s_axi_rready <= '0';
    wait until rising_edge(aclk);
    assert s_axi_arready = '1' report "CHECK pending read: the held-back read was not taken" severity failure;
    wait for 1 ns;
    s_axi_arvalid <= '0';
    s_axi_rready <= '1';
    idle(2);
    s_axi_rready <= '0';

    -- Reset in the middle: the register and the responses clear.
    axi_write(x"0", x"13572468", "1111", b_delay => 3);
    aresetn <= '0';
    idle(3);
    assert s_axi_bvalid = '0' and s_axi_rvalid = '0' report "CHECK reset left a response up" severity failure;
    aresetn <= '1';
    idle(2);
    axi_read(x"0", got);
    assert got = x"00000000" report "CHECK reset did not clear the register" severity failure;

    report "ALL TESTS PASSED" severity note;
    finished <= true;
    wait;
  end process;
end architecture sim;
