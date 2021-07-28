//
// Created by phmoll on 7/28/21.
//
#define CATCH_CONFIG_MAIN

#include <catch2/catch.hpp>
#include <cstdlib>

#include <ndn-cxx/face.hpp>
#include <ndn-cxx/security/key-chain.hpp>
#include <ndn-cxx/security/validator-null.hpp>
#include <ndn-cxx/util/logger.hpp>
#include <ndn-cxx/util/random.hpp>
#include <ndn-cxx/util/scheduler.hpp>
#include <ndn-cxx/util/time.hpp>

#include "../src/iblt.h"

TEST_CASE("Find IBLT Limit")
{

    GIVEN("An IBLT with the size of 85")
    {
        uint32_t m_expectedNumEntries = 85;
        syncps::IBLT iblt(m_expectedNumEntries);
        ndn::KeyChain m_keyChain;

        WHEN("10 entries are added") {
            for (int i = 0; i < 100; i++) {
                uint32_t entry = std::rand();
                iblt.insert(entry);
            }

            THEN("Adding the IBLT to an Interest should not raise an exception") {
                ndn::Name name("/ndn/");
                CHECK_NOTHROW(iblt.appendToName(name));

                ndn::Interest interest(name);

            }

            THEN("Adding the IBLT to an Interest should not raise an exception") {
                ndn::Name name("/ndn/");
                CHECK_NOTHROW(iblt.appendToName(name));

                ndn::Block wire;
                ndn::Interest interest(name);
                CHECK_NOTHROW(wire = interest.wireEncode());
                REQUIRE(wire.size() < 8800);
            }

            THEN("Adding the IBLT to a Data should not raise an exception") {
                ndn::Name name("/ndn/");
                CHECK_NOTHROW(iblt.appendToName(name));

                std::string content("");
                ndn::Block block = ndn::encoding::makeBinaryBlock(
                        ndn::tlv::Content, reinterpret_cast<const uint8_t*>(content.c_str()), content.size());

                ndn::Data data(name);
                data.setContent(block);
                m_keyChain.sign(data);

                std::cout << data << std::endl;

                ndn::Block wire;
                CHECK_NOTHROW(wire = data.wireEncode());
                REQUIRE(wire.size() < 8800);
                std::cout << wire.size() << std::endl;
            }

            THEN("Parsing the IBLT from a name should work") {
                ndn::Name name("/ndn/");
                CHECK_NOTHROW(iblt.appendToName(name));

                syncps::IBLT parsed(m_expectedNumEntries);
                CHECK_NOTHROW(parsed.initialize(name.get(-1)));
            }
        }
    }
}