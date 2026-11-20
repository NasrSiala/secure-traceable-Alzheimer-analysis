-- fir_decim_tb: self-checking VHDL-2008 testbench of fir_decim (T3.19, 1/2).
--
-- Run it in Vivado xsim (`make -C hw/sim xsim-fir`). It prints "FIR_DECIM_TB PASSED"
-- and stops at the first failure. Expected samples come from
-- hw/sim/vectors/fir_decim_random.txt, which tests/scripts/test_fir_decim.py
-- locks to saam.dsp.fir_fixed.filter_decimate. The bench is started with its
-- working directory in hw/sim/build/xsim-fir.
--
-- What it checks:
--   - coef_id equals the id in the vector file (the package constant);
--   - 20 int16 signals of 5055 samples, 1011 outputs each (indices 0, 5, 10, ...);
--   - clear between signals, and aresetn before signal 10, so a delay line that
--     kept the previous signal cannot match;
--   - in_ready stays low for the 112 cycles until out_valid, and out_valid is
--     one cycle.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity fir_decim_tb is
end entity fir_decim_tb;

architecture sim of fir_decim_tb is
  constant CLK_PERIOD  : time := 10 ns;
  constant VECTOR_FILE : string := "../../vectors/fir_decim_random.txt";
  constant MAC_EDGES   : natural := 112;

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

  function to_hex8(value : std_logic_vector(31 downto 0)) return string is
    constant HEX : string(1 to 16) := "0123456789abcdef";
    variable text : string(1 to 8);
    variable nibble : natural;
  begin
    for i in 0 to 7 loop
      nibble := to_integer(unsigned(value(31 - 4 * i downto 28 - 4 * i)));
      text(i + 1) := HEX(nibble + 1);
    end loop;
    return text;
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

  dut : entity work.fir_decim
    port map (
      aclk      => aclk,
      aresetn   => aresetn,
      clear     => clear,
      in_valid  => in_valid,
      in_data   => in_data,
      in_ready  => in_ready,
      out_valid => out_valid,
      out_data  => out_data,
      coef_id   => coef_id
    );

  stimulus : process
    file vectors : text open read_mode is VECTOR_FILE;

    procedure tick is
    begin
      wait until rising_edge(aclk);
    end procedure;

    procedure settle is
    begin
      wait for CLK_PERIOD / 4;
    end procedure;

    procedure read_int(variable value : out integer) is
      variable buf : line;
      variable ok : boolean;
    begin
      loop
        assert not endfile(vectors) report "truncated vector file" severity failure;
        readline(vectors, buf);
        if buf /= null and buf.all'length > 0 and buf.all(buf.all'left) /= '#' then
          read(buf, value, ok);
          assert ok report "bad integer in the vector file" severity failure;
          exit;
        end if;
      end loop;
    end procedure;

    procedure read_id(variable text : out string(1 to 8)) is
      variable buf : line;
      variable left : positive;
    begin
      loop
        assert not endfile(vectors) report "truncated vector file" severity failure;
        readline(vectors, buf);
        if buf /= null and buf.all'length >= 8 and buf.all(buf.all'left) /= '#' then
          left := buf.all'left;
          text := buf.all(left to left + 7);
          exit;
        end if;
      end loop;
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
      assert in_ready = '1' report "not ready after reset" severity failure;
      assert out_valid = '0' report "out_valid high after reset" severity failure;
    end procedure;

    procedure do_clear is
    begin
      in_valid <= '0';
      clear <= '1';
      tick;
      settle;
      clear <= '0';
      settle;
      assert in_ready = '1' report "not ready after clear" severity failure;
      assert out_valid = '0' report "out_valid high after clear" severity failure;
    end procedure;

    -- in_ready is read on the accepting edge, before the DUT updates it.
    -- out_valid is read after settle, so the registered pulse is visible.
    procedure put_sample(sample : integer; produces : boolean; variable got : out integer) is
      variable cycles : natural := 0;
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
        assert out_valid = '0' report "output on a non-decimated sample" severity failure;
        assert in_ready = '1' report "in_ready fell on a non-decimated sample" severity failure;
        got := 0;
        return;
      end if;
      settle;
      assert in_ready = '0' report "in_ready stayed high for an output sample" severity failure;
      cycles := 0;
      loop
        tick;
        settle;
        cycles := cycles + 1;
        exit when out_valid = '1';
        assert in_ready = '0' report "in_ready rose during the MAC" severity failure;
        assert cycles < 200 report "out_valid timeout" severity failure;
      end loop;
      assert cycles = MAC_EDGES
        report "MAC latency " & integer'image(cycles) & " cycles, expected 112"
        severity failure;
      got := to_integer(signed(out_data));
      tick;
      settle;
      assert out_valid = '0' report "out_valid is not a single cycle" severity failure;
    end procedure;

    variable signal_count : integer;
    variable input_length : integer;
    variable file_id : string(1 to 8);
    variable sample : integer;
    variable expected : integer;
    variable got : integer;
    variable outputs : natural;
  begin
    read_int(signal_count);
    read_int(input_length);
    read_id(file_id);
    assert signal_count = 20 report "the vector file does not hold 20 signals" severity failure;
    assert input_length = 5055 report "the vector file is not 5055 samples" severity failure;

    do_reset;
    assert to_hex8(coef_id) = file_id
      report "coef_id " & to_hex8(coef_id) & " /= " & file_id
      severity failure;

    for s in 0 to signal_count - 1 loop
      if s = 10 then
        do_reset;
      elsif s /= 0 then
        do_clear;
      end if;
      outputs := 0;
      for index in 0 to input_length - 1 loop
        read_int(sample);
        if index mod 5 = 0 then
          read_int(expected);
          put_sample(sample, true, got);
          assert got = expected
            report "signal " & integer'image(s) & " index " & integer'image(index)
              & " got " & integer'image(got) & " expected " & integer'image(expected)
            severity failure;
          outputs := outputs + 1;
        else
          put_sample(sample, false, got);
        end if;
      end loop;
      assert outputs = 1011
        report "signal " & integer'image(s) & " produced " & integer'image(outputs)
        severity failure;
    end loop;

    report "fir vectors: " & integer'image(signal_count);
    report "FIR_DECIM_TB PASSED";
    finished <= true;
    wait;
  end process;
end architecture sim;
