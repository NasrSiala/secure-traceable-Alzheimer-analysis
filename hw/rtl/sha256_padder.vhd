-- sha256_padder: FIPS 180-4 padding in hardware, then the verified sha256_core (T3.18, 2/2).
--
-- The core compresses blocks that are already padded. This block turns a message into those
-- blocks: the message bytes, a 1 bit (the byte 0x80), zeros, and the length in bits on 64 bits,
-- big-endian (FIPS 180-4 5.1.1). A message that does not leave 9 bytes at the end of its last
-- block (length mod 64 >= 56, including 56, 64 and 120) spills into one more block. Blocks are
-- handed to the core one after another, without `init` between them, so H chains.
--
-- Message side (the AXI wrapper of T3.20 will drive this; there is no AXI here):
--   init       one cycle, while idle or after done: new message. Reloads H in the core and
--              clears `done`. Ignored while a message is in progress (reset aborts one).
--   in_valid   a 32-bit word is offered. Taken when in_valid and in_ready are both 1.
--   in_data    big-endian word. The first message byte is in bits 31..24.
--   in_last    this beat ends the message. Required on the last beat, including the empty one.
--   in_bytes   valid bytes of this beat, 0 to 4, and only when in_last is 1. 0 is the empty
--              message (in_data is ignored). 4 means the whole word is message. 1..3 keep the
--              top bytes and ignore the low ones (the bench fills those with 0xFF). On a beat
--              that is not last, in_bytes is ignored and the word counts as 4 message bytes.
--   in_ready   1 while a beat can be accepted (message phase, no beat waiting, init low).
--   busy       1 from the cycle after init until done.
--   done       1 when `digest` is the hash of the whole message. Cleared by init or reset.
--   digest     the core's H0..H7, H0 in bits 255..224. Valid when done is 1.
--
-- The byte counter is 32 bits (Architecture 5.6: messages of 0 to 2^32-1 bytes). The length
-- field is the byte count times 8, placed on 64 bits. The bench exercises 0 to 4096 bytes.
--
-- Conventions: VHDL-2008, ieee.numeric_std only, one clock, synchronous active-low reset,
-- no vendor primitive. The compression function is sha256_core, not a second copy.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sha256_padder is
  port (
    aclk      : in  std_logic;
    aresetn   : in  std_logic;
    init      : in  std_logic;
    in_valid  : in  std_logic;
    in_ready  : out std_logic;
    in_data   : in  std_logic_vector(31 downto 0);
    in_last   : in  std_logic;
    in_bytes  : in  std_logic_vector(2 downto 0);
    busy      : out std_logic;
    done      : out std_logic;
    digest    : out std_logic_vector(255 downto 0)
  );
end entity sha256_padder;

architecture rtl of sha256_padder is
  type phase_t is (
    PH_IDLE, PH_MSG, PH_MARK, PH_FILL, PH_LENLO, PH_WAIT, PH_DONE
  );

  signal phase         : phase_t := PH_IDLE;
  signal after_phase   : phase_t := PH_MSG;
  signal slot          : unsigned(3 downto 0) := (others => '0');
  signal msg_len       : unsigned(31 downto 0) := (others => '0');
  signal pending_data  : std_logic_vector(31 downto 0) := (others => '0');
  signal pending_valid : std_logic := '0';

  signal core_init       : std_logic;
  signal core_word_valid : std_logic;
  signal core_word_data  : std_logic_vector(31 downto 0);
  signal core_word_ready : std_logic;
  signal core_busy       : std_logic;
  signal core_done       : std_logic;

  signal take_direct  : std_logic;
  signal take_pending : std_logic;
  signal take_pad     : std_logic;
  signal pad_word     : std_logic_vector(31 downto 0);
  signal len_hi       : std_logic_vector(31 downto 0);
  signal len_lo       : std_logic_vector(31 downto 0);

  -- The 0x80 byte sits in the first byte that is not a message byte. nbytes is 0, 1, 2 or 3
  -- (a full last word is forwarded as-is, and 0x80 is a word of its own).
  function merge_marker(data : std_logic_vector(31 downto 0); nbytes : natural)
    return std_logic_vector is
    variable word : std_logic_vector(31 downto 0) := (others => '0');
  begin
    if nbytes = 1 then
      word(31 downto 24) := data(31 downto 24);
      word(23 downto 16) := x"80";
    elsif nbytes = 2 then
      word(31 downto 16) := data(31 downto 16);
      word(15 downto 8)  := x"80";
    elsif nbytes = 3 then
      word(31 downto 8) := data(31 downto 8);
      word(7 downto 0)  := x"80";
    else
      word(31 downto 24) := x"80";
    end if;
    return word;
  end function;

begin
  -- init reaches the core only from idle or done, and never on a cycle that also sends a word.
  core_init <= '1' when init = '1' and (phase = PH_IDLE or phase = PH_DONE) else '0';

  take_direct <= '1' when phase = PH_MSG and pending_valid = '0' and in_valid = '1'
    and in_last = '0' and init = '0' and core_init = '0' and core_word_ready = '1'
    else '0';

  take_pending <= '1' when pending_valid = '1' and init = '0' and core_init = '0'
    and core_word_ready = '1' else '0';

  take_pad <= '1' when pending_valid = '0' and init = '0' and core_init = '0'
    and core_word_ready = '1'
    and (phase = PH_MARK or phase = PH_FILL or phase = PH_LENLO) else '0';

  -- Bit length = msg_len * 8, on 64 bits. The high word is zero for every message the bench sends
  -- (4096 * 8 fits in 16 bits) and is the top 3 bits of the byte count for a full 32-bit length.
  len_lo <= std_logic_vector(msg_len(28 downto 0)) & "000";
  len_hi <= std_logic_vector(resize(msg_len(31 downto 29), 32));

  pad_word <= x"80000000" when phase = PH_MARK
    else len_hi when phase = PH_FILL and slot = 14
    else len_lo when phase = PH_LENLO
    else x"00000000";

  core_word_valid <= take_direct or take_pending or take_pad;
  core_word_data  <= in_data when take_direct = '1'
    else pending_data when take_pending = '1'
    else pad_word;

  in_ready <= '1' when phase = PH_MSG and pending_valid = '0' and init = '0' else '0';
  busy     <= '1' when (phase /= PH_IDLE and phase /= PH_DONE) or core_busy = '1' else '0';
  done     <= '1' when phase = PH_DONE else '0';

  u_core : entity work.sha256_core
    port map (
      aclk       => aclk,
      aresetn    => aresetn,
      init       => core_init,
      word_valid => core_word_valid,
      word_data  => core_word_data,
      word_ready => core_word_ready,
      busy       => core_busy,
      done       => core_done,
      digest     => digest
    );

  process (aclk)
    variable nbytes : natural;
  begin
    if rising_edge(aclk) then
      if aresetn = '0' then
        phase         <= PH_IDLE;
        after_phase   <= PH_MSG;
        slot          <= (others => '0');
        msg_len       <= (others => '0');
        pending_data  <= (others => '0');
        pending_valid <= '0';
      elsif init = '1' and (phase = PH_IDLE or phase = PH_DONE) then
        phase         <= PH_MSG;
        after_phase   <= PH_MSG;
        slot          <= (others => '0');
        msg_len       <= (others => '0');
        pending_data  <= (others => '0');
        pending_valid <= '0';
      elsif take_direct = '1' then
        -- A full word that is not the end of the message, forwarded the cycle it is offered.
        msg_len <= msg_len + 4;
        slot    <= slot + 1;
      elsif take_pending = '1' then
        pending_valid <= '0';
        slot          <= slot + 1;
        phase         <= after_phase;
      elsif take_pad = '1' then
        if phase = PH_LENLO then
          phase <= PH_WAIT;
          slot  <= (others => '0');
        elsif phase = PH_FILL and slot = 14 then
          -- Eight bytes remain in this block: they are the length. A slot of 15 would be a
          -- single zero byte-word instead, and the length moves to the next block.
          phase <= PH_LENLO;
          slot  <= slot + 1;
        else
          slot <= slot + 1;
          if phase = PH_MARK then
            phase <= PH_FILL;
          end if;
        end if;
      elsif init = '0' and phase = PH_MSG and pending_valid = '0' and in_valid = '1'
        and in_last = '1' then
        nbytes := to_integer(unsigned(in_bytes));
        if nbytes <= 4 then
          msg_len <= msg_len + nbytes;
          if nbytes = 4 then
            pending_data <= in_data;
            after_phase  <= PH_MARK;
          else
            pending_data <= merge_marker(in_data, nbytes);
            after_phase  <= PH_FILL;
          end if;
          pending_valid <= '1';
        end if;
      elsif init = '0' and phase = PH_MSG and pending_valid = '0' and in_valid = '1'
        and in_last = '0' then
        -- The core is compressing. Hold this one word until it can take the next block.
        pending_data  <= in_data;
        pending_valid <= '1';
        after_phase   <= PH_MSG;
        msg_len       <= msg_len + 4;
      elsif phase = PH_WAIT and core_done = '1' then
        phase <= PH_DONE;
      end if;
    end if;
  end process;
end architecture rtl;
