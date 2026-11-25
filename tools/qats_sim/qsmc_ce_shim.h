// qsmc_ce_shim.h - host-only API additions for the confirmation-engine native harness.
//
// This header wraps the typed MQL5 shim used by QATS and the chart-object shim
// used by QSVP. It supplies the handful of terminal APIs the new confirmation EA
// needs that the older simulators did not model:
//
//   * StringGetCharacter (raw byte view; sufficient for the ASCII parser and for
//     the UTF-8 en-dash normalisation path in the test driver)
//   * a bounded in-memory FILE_COMMON file table for the opinion/CSV/registry
//     snapshots (no disk I/O; the real EA still uses MetaTrader file functions)
//   * a deterministic read-delay hook so an AI timeout can be exercised without
//     sleeping the test process
//   * M1 series support and CTrade::PositionClosePartial, both added directly to
//     mql5_shim.h so the EA source is compiled unchanged.
//
// This is NOT MetaEditor, NOT Strategy Tester and NOT a live terminal.
#pragma once
#pragma GCC system_header

#include "mql5_shim.h"
#include "mql5_chart.h"

#include <string>
#include <map>

#ifndef FILE_READ
#define FILE_READ      0x0001
#define FILE_WRITE     0x0002
#define FILE_TXT       0x0004
#define FILE_COMMON    0x0008
#define FILE_ANSI      0x0010
#define FILE_SHARE_READ 0x0020
#define SEEK_END       2
#endif

// MQL5's StringGetCharacter returns a UTF-16 code unit. The host string is
// UTF-8, so this shim returns the unsigned byte at the same position. The EA's
// character tests use ASCII values and normalise Unicode dashes with
// StringReplace before character scanning, so both runtimes agree on the data
// the parser actually consumes.
inline ushort StringGetCharacter(const string &s, const int pos)
{
   if(pos < 0 || pos >= (int)s.size())
   {
      return 0;
   }
   return (ushort)(unsigned char)s[(size_t)pos];
}

namespace qsmc_ce
{
struct FileState
{
   string path;
   string content;
   size_t pos;
   bool writing;
   bool delay_pending;
};

inline std::map<string, string> &files()
{
   static std::map<string, string> m;
   return m;
}

inline std::map<int, FileState> &open_files()
{
   static std::map<int, FileState> m;
   return m;
}

inline int &next_handle()
{
   static int h = 1;
   return h;
}

inline uint &tick_offset_ms()
{
   static uint v = 0;
   return v;
}

inline uint &configured_read_delay_ms()
{
   static uint v = 0;
   return v;
}

inline void reset_files()
{
   files().clear();
   open_files().clear();
   next_handle() = 1;
   tick_offset_ms() = 0;
   configured_read_delay_ms() = 0;
}

inline void set_file(const string &path, const string &content)
{
   files()[path] = content;
}

inline bool has_file(const string &path)
{
   return files().find(path) != files().end();
}

inline string get_file(const string &path)
{
   auto it = files().find(path);
   return it == files().end() ? string() : it->second;
}

inline void set_read_delay_ms(const uint delay)
{
   configured_read_delay_ms() = delay;
}

inline uint tick_count_ms()
{
   return (uint)((unsigned long)sim::S.now * 1000UL) + tick_offset_ms();
}

inline void apply_read_delay_once(FileState &st)
{
   if(st.delay_pending && configured_read_delay_ms() > 0)
   {
      tick_offset_ms() += configured_read_delay_ms();
      st.delay_pending = false;
   }
}

inline void commit_file(FileState &st)
{
   if(st.writing)
   {
      files()[st.path] = st.content;
   }
}
} // namespace qsmc_ce

inline int FileOpen(const string path, const int flags)
{
   const bool read = (flags & FILE_READ) != 0;
   const bool write = (flags & FILE_WRITE) != 0;
   if(read && !qsmc_ce::has_file(path))
   {
      return INVALID_HANDLE;
   }
   if(read == false && write == false)
   {
      return INVALID_HANDLE;
   }
   qsmc_ce::FileState st{};
   st.path = path;
   st.pos = 0;
   st.writing = write;
   st.delay_pending = read;
   st.content = read ? qsmc_ce::get_file(path) : string();
   int h = qsmc_ce::next_handle()++;
   qsmc_ce::open_files()[h] = st;
   return h;
}

inline bool FileIsEnding(const int handle)
{
   auto it = qsmc_ce::open_files().find(handle);
   if(it == qsmc_ce::open_files().end())
   {
      return true;
   }
   return it->second.pos >= it->second.content.size();
}

inline string FileReadString(const int handle)
{
   auto it = qsmc_ce::open_files().find(handle);
   if(it == qsmc_ce::open_files().end())
   {
      return "";
   }
   qsmc_ce::FileState &st = it->second;
   if(st.writing || st.pos >= st.content.size())
   {
      return "";
   }
   qsmc_ce::apply_read_delay_once(st);
   size_t nl = st.content.find('\n', st.pos);
   size_t end = (nl == string::npos) ? st.content.size() : nl;
   string out = st.content.substr(st.pos, end - st.pos);
   st.pos = (nl == string::npos) ? st.content.size() : nl + 1;
   return out;
}

inline uint FileWriteString(const int handle, const string &text)
{
   auto it = qsmc_ce::open_files().find(handle);
   if(it == qsmc_ce::open_files().end() || it->second.writing == false)
   {
      return 0;
   }
   it->second.content += text;
   return (uint)text.size();
}

inline bool FileFlush(const int handle)
{
   auto it = qsmc_ce::open_files().find(handle);
   if(it == qsmc_ce::open_files().end())
   {
      return false;
   }
   qsmc_ce::commit_file(it->second);
   return true;
}

inline void FileClose(const int handle)
{
   auto it = qsmc_ce::open_files().find(handle);
   if(it == qsmc_ce::open_files().end())
   {
      return;
   }
   qsmc_ce::commit_file(it->second);
   qsmc_ce::open_files().erase(it);
}

// Rebind GetTickCount only AFTER the shim and chart headers are included. The
// EA's two calls then see the deterministic read-delay offset; no sleeping is
// needed to prove the 250 ms opinion deadline.
#undef GetTickCount
#define GetTickCount() qsmc_ce::tick_count_ms()
