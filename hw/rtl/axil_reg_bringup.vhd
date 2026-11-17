-- axil_reg_bringup: one 32-bit read/write register behind an AXI4-Lite slave (T1.9, l10).
--
-- Only for the Zybo bring-up: it proves that the PS reaches the PL over M_AXI_GP0 and reads back
-- what it wrote. It is not the register map of a core (Architecture 5.6) and is replaced by the
-- AXI wrappers of T3.20.
--
--   0x0  DATA   R/W  32 bits, byte strobes honoured, reset value 0
--   0x4+ (reads as 0, writes ignored)
--
-- Conventions of the hardware part: VHDL-2008, ieee.numeric_std only, one clock, synchronous
-- active-low reset (aresetn), no vendor primitive. The two attributes below only tell the Vivado
-- block design which clock and reset belong to the bus; any other tool ignores them.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity axil_reg_bringup is
  port (
    aclk          : in  std_logic;
    aresetn       : in  std_logic;
    -- write address
    s_axi_awaddr  : in  std_logic_vector(3 downto 0);
    s_axi_awprot  : in  std_logic_vector(2 downto 0);
    s_axi_awvalid : in  std_logic;
    s_axi_awready : out std_logic;
    -- write data
    s_axi_wdata   : in  std_logic_vector(31 downto 0);
    s_axi_wstrb   : in  std_logic_vector(3 downto 0);
    s_axi_wvalid  : in  std_logic;
    s_axi_wready  : out std_logic;
    -- write response
    s_axi_bresp   : out std_logic_vector(1 downto 0);
    s_axi_bvalid  : out std_logic;
    s_axi_bready  : in  std_logic;
    -- read address
    s_axi_araddr  : in  std_logic_vector(3 downto 0);
    s_axi_arprot  : in  std_logic_vector(2 downto 0);
    s_axi_arvalid : in  std_logic;
    s_axi_arready : out std_logic;
    -- read data
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
end entity axil_reg_bringup;

architecture rtl of axil_reg_bringup is
  signal data_reg  : std_logic_vector(31 downto 0);
  signal rdata_reg : std_logic_vector(31 downto 0);
  signal bvalid_r  : std_logic;
  signal rvalid_r  : std_logic;
  signal write_ok  : std_logic;
  signal read_ok   : std_logic;
begin
  -- A write is taken when the address and the data are both offered and no response is pending.
  write_ok <= s_axi_awvalid and s_axi_wvalid and not bvalid_r;
  -- A read is taken when the address is offered and no read data is pending.
  read_ok <= s_axi_arvalid and not rvalid_r;

  s_axi_awready <= write_ok;
  s_axi_wready  <= write_ok;
  s_axi_bresp   <= "00";
  s_axi_bvalid  <= bvalid_r;
  s_axi_arready <= read_ok;
  s_axi_rdata   <= rdata_reg;
  s_axi_rresp   <= "00";
  s_axi_rvalid  <= rvalid_r;

  process (aclk)
  begin
    if rising_edge(aclk) then
      if aresetn = '0' then
        data_reg  <= (others => '0');
        rdata_reg <= (others => '0');
        bvalid_r  <= '0';
        rvalid_r  <= '0';
      else
        if write_ok = '1' then
          if s_axi_awaddr(3 downto 2) = "00" then
            for byte in 0 to 3 loop
              if s_axi_wstrb(byte) = '1' then
                data_reg(8 * byte + 7 downto 8 * byte) <= s_axi_wdata(8 * byte + 7 downto 8 * byte);
              end if;
            end loop;
          end if;
          bvalid_r <= '1';
        elsif bvalid_r = '1' and s_axi_bready = '1' then
          bvalid_r <= '0';
        end if;

        if read_ok = '1' then
          if s_axi_araddr(3 downto 2) = "00" then
            rdata_reg <= data_reg;
          else
            rdata_reg <= (others => '0');
          end if;
          rvalid_r <= '1';
        elsif rvalid_r = '1' and s_axi_rready = '1' then
          rvalid_r <= '0';
        end if;
      end if;
    end if;
  end process;
end architecture rtl;
