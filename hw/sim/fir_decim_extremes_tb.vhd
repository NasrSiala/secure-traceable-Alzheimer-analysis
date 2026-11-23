-- fir_decim_extremes_tb: AC-16.4 on the direct FIR port (T3.19, 2/2).
-- 111 samples of +32767, then reset, then 111 samples of -32768.
-- Expected values are fir_fixed.filter_decimate, locked by tests/scripts/test_fir_decim.py.
-- Prints "FIR_DECIM_EXTREMES_TB PASSED".

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity fir_decim_extremes_tb is
end entity fir_decim_extremes_tb;

architecture sim of fir_decim_extremes_tb is
  constant CLK_PERIOD : time := 10 ns;
  type sample_list is array (0 to 22) of integer;
  constant HI : sample_list := (
    -41, 146, 484, 127, 675, -18, 720, 121, 290, 1045, -1825, 19634,
    32767, 31765, 32767, 32767, 32767, 32767, 32767, 32767, 32767, 32767, 32767
  );
  constant LO : sample_list := (
    41, -146, -484, -127, -675, 18, -720, -121, -290, -1045, 1825, -19635,
    -32768, -31766, -32768, -32768, -32768, -32768, -32768, -32768,
    -32768, -32768, -32768
  );

  signal aclk      : std_logic := '0';
  signal aresetn   : std_logic := '0';
  signal clear     : std_logic := '0';
  signal in_valid  : std_logic := '0';
  signal in_ready  : std_logic;
  signal in_data   : std_logic_vector(15 downto 0) := (others => '0');
  signal out_valid : std_logic;
  signal out_data  : std_logic_vector(15 downto 0);
  signal coef_id   : std_logic_vector(31 downto 0);
  signal finished  : boolean := false;
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

  dut : entity work.fir_decim
    port map (
      aclk => aclk, aresetn => aresetn, clear => clear,
      in_valid => in_valid, in_data => in_data, in_ready => in_ready,
      out_valid => out_valid, out_data => out_data, coef_id => coef_id
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

    procedure do_reset is
    begin
      in_valid <= '0';
      clear <= '0';
      aresetn <= '0';
      tick;
      settle;
      tick;
      settle;
      aresetn <= '1';
      settle;
    end procedure;

    procedure put_sample(sample : integer; produces : boolean; expected : integer) is
      variable cycles : natural := 0;
      variable got : integer;
    begin
      in_data <= std_logic_vector(to_signed(sample, 16));
      in_valid <= '1';
      loop
        tick;
        exit when in_ready = '1';
        cycles := cycles + 1;
        assert cycles < 400 report "in_ready stayed low" severity failure;
      end loop;
      in_valid <= '0';
      if not produces then
        settle;
        assert out_valid = '0' report "unexpected extreme output" severity failure;
        return;
      end if;
      cycles := 0;
      loop
        tick;
        settle;
        cycles := cycles + 1;
        exit when out_valid = '1';
        assert cycles < 200 report "out_valid timeout" severity failure;
      end loop;
      got := to_integer(signed(out_data));
      assert got = expected
        report "extreme mismatch, got " & integer'image(got)
        severity failure;
      assert got >= -32768 and got <= 32767 report "output left int16" severity failure;
      tick;
      settle;
      assert out_valid = '0' report "out_valid is not one cycle" severity failure;
    end procedure;

    variable produced : natural;
  begin
    do_reset;
    produced := 0;
    for index in 0 to 110 loop
      if index mod 5 = 0 then
        put_sample(32767, true, HI(produced));
        produced := produced + 1;
      else
        put_sample(32767, false, 0);
      end if;
    end loop;
    assert produced = 23 report "positive extreme output count" severity failure;
    assert HI(12) = 32767 and HI(22) = 32767 report "positive rail missing" severity failure;

    do_reset;
    produced := 0;
    for index in 0 to 110 loop
      if index mod 5 = 0 then
        put_sample(-32768, true, LO(produced));
        produced := produced + 1;
      else
        put_sample(-32768, false, 0);
      end if;
    end loop;
    assert produced = 23 report "negative extreme output count" severity failure;
    assert LO(12) = -32768 and LO(22) = -32768 report "negative rail missing" severity failure;

    report "FIR_DECIM_EXTREMES_TB PASSED";
    finished <= true;
    wait;
  end process;
end architecture sim;
