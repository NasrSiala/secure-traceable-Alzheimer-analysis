-- sha256_axi: AXI4-Lite wrapper around sha256_padder (T3.20, 1/2, IF-15).
--
-- Register map (Architecture §5.6). Addresses are bytes. A write to a read-only
-- register gets OKAY and changes nothing. CTRL bits are pulses, not stored.
--
--   0x00 CTRL       W  bit0 INIT (one cycle, new message); bit1 FINAL
--   0x04 STATUS     R  bit0 READY, bit1 BUSY, bit2 DONE
--   0x08 DATA_IN    W  big-endian message word
--   0x0C LAST_BYTES W  valid bytes of the final word, 0 to 4
--   0x10-0x2C DIGEST0-7 R  H0..H7, DIGEST0 is the first four digest bytes
--   0x30 VERSION    R  generic VERSION (the git SHA when the bitstream is built)
--
-- FINAL with LAST_BYTES = 0 sends the empty message. Otherwise FINAL applies to
-- the next DATA_IN. DATA_IN is accepted only while READY is 1.
--
-- Conventions: VHDL-2008, ieee.numeric_std only, one clock, synchronous
-- active-low reset, no vendor primitive. The hash is sha256_padder.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sha256_axi is
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
end entity sha256_axi;

architecture rtl of sha256_axi is
  signal bvalid_r    : std_logic := '0';
  signal rvalid_r    : std_logic := '0';
  signal rdata_r     : std_logic_vector(31 downto 0) := (others => '0');
  signal init_pulse  : std_logic := '0';
  signal final_next  : std_logic := '0';
  signal empty_req   : std_logic := '0';
  signal last_bytes  : unsigned(2 downto 0) := (others => '0');
  signal beat_valid  : std_logic := '0';
  signal beat_last   : std_logic := '0';
  signal beat_data   : std_logic_vector(31 downto 0) := (others => '0');
  signal beat_bytes  : std_logic_vector(2 downto 0) := (others => '0');
  signal pad_ready   : std_logic;
  signal pad_busy    : std_logic;
  signal pad_done    : std_logic;
  signal digest      : std_logic_vector(255 downto 0);
  signal write_word  : unsigned(5 downto 0);
  signal read_word   : unsigned(5 downto 0);
  signal write_ok    : std_logic;
  signal read_ok     : std_logic;
  signal data_write  : std_logic;
  signal status_word : std_logic_vector(31 downto 0);
begin
  write_word <= unsigned(s_axi_awaddr(7 downto 2));
  read_word  <= unsigned(s_axi_araddr(7 downto 2));
  data_write <= '1' when write_word = 2 else '0';

  -- DATA_IN waits until the padder can take a beat. Other writes complete at once.
  write_ok <= s_axi_awvalid and s_axi_wvalid and not bvalid_r
    and not beat_valid and not init_pulse
    and (not data_write or (pad_ready and not empty_req));

  read_ok <= s_axi_arvalid and not rvalid_r;

  s_axi_awready <= write_ok;
  s_axi_wready  <= write_ok;
  s_axi_bresp   <= "00";
  s_axi_bvalid  <= bvalid_r;
  s_axi_arready <= read_ok;
  s_axi_rdata   <= rdata_r;
  s_axi_rresp   <= "00";
  s_axi_rvalid  <= rvalid_r;

  status_word <= (
    0 => pad_ready and not beat_valid and not init_pulse and not empty_req,
    1 => pad_busy,
    2 => pad_done,
    others => '0'
  );

  u_pad : entity work.sha256_padder
    port map (
      aclk      => aclk,
      aresetn   => aresetn,
      init      => init_pulse,
      in_valid  => beat_valid,
      in_ready  => pad_ready,
      in_data   => beat_data,
      in_last   => beat_last,
      in_bytes  => beat_bytes,
      busy      => pad_busy,
      done      => pad_done,
      digest    => digest
    );

  control : process (aclk)
    variable word    : integer;
    variable nbytes  : integer;
    variable do_init : std_logic;
  begin
    if rising_edge(aclk) then
      if aresetn = '0' then
        bvalid_r   <= '0';
        rvalid_r   <= '0';
        rdata_r    <= (others => '0');
        init_pulse <= '0';
        final_next <= '0';
        empty_req  <= '0';
        last_bytes <= (others => '0');
        beat_valid <= '0';
        beat_last  <= '0';
        beat_data  <= (others => '0');
        beat_bytes <= (others => '0');
      else
        do_init := '0';
        init_pulse <= '0';
        if beat_valid = '1' and pad_ready = '1' then
          beat_valid <= '0';
        end if;

        if write_ok = '1' then
          word := to_integer(write_word);
          if word = 0 then
            if s_axi_wdata(0) = '1' then
              do_init := '1';
              init_pulse <= '1';
            end if;
            if s_axi_wdata(1) = '1' then
              if last_bytes = 0 then
                empty_req <= '1';
              else
                final_next <= '1';
              end if;
            end if;
          elsif word = 2 and pad_ready = '1' then
            beat_data <= s_axi_wdata;
            beat_last <= final_next;
            if final_next = '1' then
              beat_bytes <= std_logic_vector(last_bytes);
              final_next <= '0';
            else
              beat_bytes <= (others => '0');
            end if;
            beat_valid <= '1';
          elsif word = 3 then
            nbytes := to_integer(unsigned(s_axi_wdata));
            if nbytes <= 4 then
              last_bytes <= to_unsigned(nbytes, 3);
            end if;
          end if;
          bvalid_r <= '1';
        elsif bvalid_r = '1' and s_axi_bready = '1' then
          bvalid_r <= '0';
        end if;

        -- The empty message is one beat, and never on the init cycle.
        if empty_req = '1' and do_init = '0' and init_pulse = '0'
          and beat_valid = '0' and pad_ready = '1' then
          beat_data  <= (others => '0');
          beat_last  <= '1';
          beat_bytes <= (others => '0');
          beat_valid <= '1';
          empty_req  <= '0';
        end if;

        if read_ok = '1' then
          word := to_integer(read_word);
          if word = 1 then
            rdata_r <= status_word;
          elsif word = 4 then
            rdata_r <= digest(255 downto 224);
          elsif word = 5 then
            rdata_r <= digest(223 downto 192);
          elsif word = 6 then
            rdata_r <= digest(191 downto 160);
          elsif word = 7 then
            rdata_r <= digest(159 downto 128);
          elsif word = 8 then
            rdata_r <= digest(127 downto 96);
          elsif word = 9 then
            rdata_r <= digest(95 downto 64);
          elsif word = 10 then
            rdata_r <= digest(63 downto 32);
          elsif word = 11 then
            rdata_r <= digest(31 downto 0);
          elsif word = 12 then
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
