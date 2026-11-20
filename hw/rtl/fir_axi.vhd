-- fir_axi: AXI4-Lite wrapper around fir_decim (T3.20, 2/2, IF-16).
--
--   0x00 CTRL     W  bit0 CLEAR, one cycle, empties the delay line
--   0x04 STATUS   R  bit0 IN_READY, bit1 OUT_VALID
--   0x08 DATA_IN  W  int16 sample in bits 15..0
--   0x0C DATA_OUT R  sign-extended int16; the read consumes the sample
--   0x10 COEF_ID  R  fir_coef_id
--   0x14 VERSION  R  generic VERSION
--
-- A write to a read-only register gets OKAY and changes nothing. DATA_IN is
-- accepted only while IN_READY is 1. An unread output holds IN_READY low so
-- the next sample cannot overwrite it.
--
-- Conventions: VHDL-2008, ieee.numeric_std only, one clock, synchronous
-- active-low reset, no vendor primitive.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity fir_axi is
  generic (
    VERSION : std_logic_vector(31 downto 0) := x"00000000"
  );
  port (
    aclk          : in  std_logic;
    aresetn       : in  std_logic;
    s_axi_awaddr  : in  std_logic_vector(7 downto 0);
    s_axi_awprot  : in  std_logic_vector(2 downto 0);
    s_axi_awvalid : in  std_logic;
    s_axi_awready : out std_logic;
    s_axi_wdata   : in  std_logic_vector(31 downto 0);
    s_axi_wstrb   : in  std_logic_vector(3 downto 0);
    s_axi_wvalid  : in  std_logic;
    s_axi_wready  : out std_logic;
    s_axi_bresp   : out std_logic_vector(1 downto 0);
    s_axi_bvalid  : out std_logic;
    s_axi_bready  : in  std_logic;
    s_axi_araddr  : in  std_logic_vector(7 downto 0);
    s_axi_arprot  : in  std_logic_vector(2 downto 0);
    s_axi_arvalid : in  std_logic;
    s_axi_arready : out std_logic;
    s_axi_rdata   : out std_logic_vector(31 downto 0);
    s_axi_rresp   : out std_logic_vector(1 downto 0);
    s_axi_rvalid  : out std_logic;
    s_axi_rready  : in  std_logic
  );

  attribute X_INTERFACE_INFO      : string;
  attribute X_INTERFACE_PARAMETER : string;
  attribute X_INTERFACE_INFO of aclk : signal is "xilinx.com:signal:clock:1.0 aclk CLK";
  attribute X_INTERFACE_PARAMETER of aclk : signal is
    "ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET aresetn";
  attribute X_INTERFACE_INFO of aresetn : signal is "xilinx.com:signal:reset:1.0 aresetn RST";
  attribute X_INTERFACE_PARAMETER of aresetn : signal is "POLARITY ACTIVE_LOW";
end entity fir_axi;

architecture rtl of fir_axi is
  signal bvalid_r     : std_logic := '0';
  signal rvalid_r     : std_logic := '0';
  signal rdata_r      : std_logic_vector(31 downto 0) := (others => '0');
  signal clear_pulse  : std_logic := '0';
  signal sample_valid : std_logic := '0';
  signal sample_data  : std_logic_vector(15 downto 0) := (others => '0');
  signal out_hold     : std_logic := '0';
  signal out_hold_data : std_logic_vector(15 downto 0) := (others => '0');
  signal fir_ready    : std_logic;
  signal fir_valid    : std_logic;
  signal fir_data     : std_logic_vector(15 downto 0);
  signal coef_id      : std_logic_vector(31 downto 0);
  signal write_word   : unsigned(5 downto 0);
  signal read_word    : unsigned(5 downto 0);
  signal write_ok     : std_logic;
  signal read_ok      : std_logic;
  signal data_write   : std_logic;
  signal in_ready_bit : std_logic;
  signal consume      : std_logic;
begin
  write_word <= unsigned(s_axi_awaddr(7 downto 2));
  read_word  <= unsigned(s_axi_araddr(7 downto 2));
  data_write <= '1' when write_word = 2 else '0';
  in_ready_bit <= fir_ready and not sample_valid and not out_hold and not clear_pulse;

  write_ok <= s_axi_awvalid and s_axi_wvalid and not bvalid_r
    and (not data_write or in_ready_bit);
  read_ok <= s_axi_arvalid and not rvalid_r;
  consume <= '1' when read_ok = '1' and read_word = 3 and out_hold = '1' else '0';

  s_axi_awready <= write_ok;
  s_axi_wready  <= write_ok;
  s_axi_bresp   <= "00";
  s_axi_bvalid  <= bvalid_r;
  s_axi_arready <= read_ok;
  s_axi_rdata   <= rdata_r;
  s_axi_rresp   <= "00";
  s_axi_rvalid  <= rvalid_r;

  u_fir : entity work.fir_decim
    port map (
      aclk      => aclk,
      aresetn   => aresetn,
      clear     => clear_pulse,
      in_valid  => sample_valid,
      in_data   => sample_data,
      in_ready  => fir_ready,
      out_valid => fir_valid,
      out_data  => fir_data,
      coef_id   => coef_id
    );

  control : process (aclk)
    variable word : integer;
    variable wide : std_logic_vector(31 downto 0);
  begin
    if rising_edge(aclk) then
      if aresetn = '0' then
        bvalid_r      <= '0';
        rvalid_r      <= '0';
        rdata_r       <= (others => '0');
        clear_pulse   <= '0';
        sample_valid  <= '0';
        sample_data   <= (others => '0');
        out_hold      <= '0';
        out_hold_data <= (others => '0');
      else
        clear_pulse <= '0';
        if sample_valid = '1' and fir_ready = '1' then
          sample_valid <= '0';
        end if;
        if fir_valid = '1' then
          out_hold_data <= fir_data;
          out_hold <= '1';
        end if;
        if consume = '1' then
          out_hold <= '0';
        end if;

        if write_ok = '1' then
          word := to_integer(write_word);
          if word = 0 and s_axi_wdata(0) = '1' then
            clear_pulse <= '1';
            sample_valid <= '0';
            out_hold <= '0';
          elsif word = 2 and in_ready_bit = '1' then
            sample_data <= s_axi_wdata(15 downto 0);
            sample_valid <= '1';
          end if;
          bvalid_r <= '1';
        elsif bvalid_r = '1' and s_axi_bready = '1' then
          bvalid_r <= '0';
        end if;

        if read_ok = '1' then
          word := to_integer(read_word);
          if word = 1 then
            rdata_r <= (0 => in_ready_bit, 1 => out_hold, others => '0');
          elsif word = 3 then
            if out_hold = '1' then
              wide := (others => out_hold_data(15));
              wide(15 downto 0) := out_hold_data;
              rdata_r <= wide;
            else
              rdata_r <= (others => '0');
            end if;
          elsif word = 4 then
            rdata_r <= coef_id;
          elsif word = 5 then
            rdata_r <= VERSION;
          else
            rdata_r <= (others => '0');
          end if;
          rvalid_r <= '1';
        elsif rvalid_r = '1' and s_axi_rready = '1' then
          rvalid_r <= '0';
        end if;
      end if;
    end if;
  end process;
end architecture rtl;
