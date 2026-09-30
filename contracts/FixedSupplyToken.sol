// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @title FixedSupplyToken
/// @notice Mints `supply` once, to `recipient`. There is no owner and no further mint.
/// @dev Reference for a public testnet deploy. See docs/MEME_COIN.md and docs/DEPLOYMENT.md.
contract FixedSupplyToken is ERC20 {
    error ZeroAddress();
    error ZeroSupply();

    constructor(string memory name_, string memory symbol_, uint256 supply, address recipient)
        ERC20(name_, symbol_)
    {
        if (recipient == address(0)) revert ZeroAddress();
        if (supply == 0) revert ZeroSupply();
        _mint(recipient, supply);
    }
}
