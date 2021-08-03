//
// Created by phmoll on 7/26/21.
//

#include "AbstractProgram.h"

bool receivedSigInt = false;

void AbstractProgram::fetchOutStandingVoiceSegements(ndn::Name name, int finalBlockId) {
    ndn::Name withoutSegmentNo = name.getPrefix(name.size() - 1);

    for (int i = 1; i <= finalBlockId; i++) {
        ndn::Name toFetch(withoutSegmentNo);
        toFetch.appendSegment(i);

        ndn::Interest interest(toFetch);
        interest.setCanBePrefix(true);
        face.expressInterest(interest,
                             bind(&AbstractProgram::onData, this, _1, _2),
                             bind(&AbstractProgram::onNack, this, _1, _2),
                             bind(&AbstractProgram::onTimeout, this, _1));
    }
}

void AbstractProgram::positionDataPublishingLoop() {
    while (m_running) {
        int delay = m_positionDataIntervalDist(m_rng);
        std::this_thread::sleep_for(std::chrono::milliseconds(delay));
        publishPositionData();
    }
}

void AbstractProgram::publishPositionData() {
    // Abort if received one interrupt
    if (receivedSigInt) return;

    // Generate a block of random Data
    std::array<__uint8_t, 16> buf{};
    ndn::random::generateSecureBytes(buf.data(), buf.size());
    ndn::Block block = ndn::encoding::makeBinaryBlock(
            ndn::tlv::Content, buf.data(), buf.size());

    // Data packet
    ndn::Name name("/position");
    name.append(m_participantPrefix);
    name.appendTimestamp();

    std::shared_ptr<ndn::Data> data = std::make_shared<ndn::Data>(name);
    data->setContent(block);
    data->setFreshnessPeriod(ndn::time::milliseconds(1000));
    m_keyChain.sign(*data, m_signingInfo);

    m_dataStore.insert(*data);

    // Publishposition Data using publish channel
    publishData(*data);
    BOOST_LOG_TRIVIAL(info) << "PUBL_MSG::" << name.toUri();

    // Todo: Log published Data
    std::cout << "Publish position data: " << data->getName() << " (" << buf.size() << " bytes)" << std::endl;
}

void AbstractProgram::voiceDataPublishingLoop() {
    while (m_running) {
        int delay = m_voiceDataIntervalDist(m_rng);
        std::this_thread::sleep_for(std::chrono::milliseconds(delay));
        publishVoiceData();
    }
}

void AbstractProgram::publishVoiceData() {
    // Abort if received one interrupt
    if (receivedSigInt) return;

    // Number of data segments
    int voiceSize = m_voiceDataSizeDist(m_rng);

    ndn::Name name("/voice");
    name.append(m_participantPrefix);
    name.appendTimestamp();
    name.appendVersion(0);

    // Create all data segments
    for (int i = 0; i < voiceSize; i++) {

        // Generate a block of random Data
        std::array<__uint8_t, 1000> buf{};
        ndn::random::generateSecureBytes(buf.data(), voiceSize);
        ndn::Block block = ndn::encoding::makeBinaryBlock(
                ndn::tlv::Content, buf.data(), voiceSize);

        // Data packet
        ndn::Name realName(name);
        realName.appendSegment(i);

        std::shared_ptr<ndn::Data> data = std::make_shared<ndn::Data>(realName);
        data->setContent(block);
        data->setFreshnessPeriod(ndn::time::milliseconds(1000));
        data->setFinalBlock(ndn::name::Component::fromNumber(voiceSize - 1));
        m_keyChain.sign(*data, m_signingInfo);

        m_dataStore.insert(*data);

        // Publish first segment of voice data using publish channel
        if (i == 0) {
            publishData(*data);
            BOOST_LOG_TRIVIAL(info) << "PUBL_MSG::" << realName.toUri();
            std::cout << "Publish voice data: " << data->getName() << " (" << buf.size() * voiceSize << " bytes)"
                      << std::endl;
        }

        // Todo: Log published Data
    }
}


