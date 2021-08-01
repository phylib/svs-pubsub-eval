#ifndef EVAL_LOG_HPP
#define EVAL_LOG_HPP

#define BOOST_LOG_DYN_LINK 1

#include <boost/log/core.hpp>
#include <boost/log/trivial.hpp>
#include <boost/log/utility/setup/common_attributes.hpp>
#include <boost/log/utility/setup/file.hpp>

namespace logging = boost::log;
namespace keywords = boost::log::keywords;

inline void initlogger(std::string filename) {
	logging::add_common_attributes();
	logging::add_file_log
	(
		keywords::file_name = filename,
		keywords::format = "\"%TimeStamp%\", \"%ProcessID%\", \"%ThreadID%\", \"%Message%\"",
		keywords::open_mode = std::ios_base::app,
		keywords::auto_flush = true
	);
}
#endif
