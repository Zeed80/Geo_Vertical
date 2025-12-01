<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

<!-- (c) 2016, Trimble Inc. All rights reserved.                                               -->
<!-- Permission is hereby granted to use, copy, modify, or distribute this style sheet for any -->
<!-- purpose and without fee, provided that the above copyright notice appears in all copies   -->
<!-- and that both the copyright notice and the limited warranty and restricted rights notice  -->
<!-- below appear in all supporting documentation.                                             -->

<!-- TRIMBLE INC. PROVIDES THIS STYLE SHEET "AS IS" AND WITH ALL FAULTS.                       -->
<!-- TRIMBLE INC. SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY               -->
<!-- OR FITNESS FOR A PARTICULAR USE. TRIMBLE INC. DOES NOT WARRANT THAT THE                   -->
<!-- OPERATION OF THIS STYLE SHEET WILL BE UNINTERRUPTED OR ERROR FREE.                        -->

<xsl:output method="text" omit-xml-declaration="yes" encoding="ISO-8859-1"/>

<!-- Set the numeric display details i.e. decimal point, thousands separator etc -->
<xsl:variable name="DecPt" select="'.'"/>    <!-- Change as appropriate for US/European -->
<xsl:variable name="GroupSep" select="','"/> <!-- Change as appropriate for US/European -->
<!-- Also change decimal-separator & grouping-separator in decimal-format below 
     as appropriate for US/European output -->
<xsl:decimal-format name="Standard" 
                    decimal-separator="."
                    grouping-separator=","
                    infinity="Infinity"
                    minus-sign="-"
                    NaN="?"
                    percent="%"
                    per-mille="&#2030;"
                    zero-digit="0" 
                    digit="#" 
                    pattern-separator=";" />

<xsl:variable name="DecPl0" select="'#0'"/>
<xsl:variable name="DecPl1" select="concat('#0', $DecPt, '0')"/>
<xsl:variable name="DecPl2" select="concat('#0', $DecPt, '00')"/>
<xsl:variable name="DecPl3" select="concat('#0', $DecPt, '000')"/>
<xsl:variable name="DecPl4" select="concat('#0', $DecPt, '0000')"/>
<xsl:variable name="DecPl5" select="concat('#0', $DecPt, '00000')"/>
<xsl:variable name="DecPl8" select="concat('#0', $DecPt, '00000000')"/>

<xsl:variable name="DegreesSymbol" select="'&#0176;'"/>
<xsl:variable name="MinutesSymbol"><xsl:text>'</xsl:text></xsl:variable>
<xsl:variable name="SecondsSymbol" select="'&quot;'"/>

<xsl:variable name="fileExt" select="'dat'"/>

<xsl:variable name="userField1" select="'FormatType|M5 file type|stringMenu|2|Default 3600 markings|Default 3300 markings'"/>
<xsl:variable name="FormatType" select="'Default 3600 markings'"/>

<!-- **************************************************************** -->
<!-- Set global variables from the Environment section of JobXML file -->
<!-- **************************************************************** -->
<xsl:variable name="DistUnit"   select="/JOBFile/Environment/DisplaySettings/DistanceUnits" />
<xsl:variable name="AngleUnit"  select="/JOBFile/Environment/DisplaySettings/AngleUnits" />
<xsl:variable name="CoordOrder" select="/JOBFile/Environment/DisplaySettings/CoordinateOrder" />
<xsl:variable name="TempUnit"   select="/JOBFile/Environment/DisplaySettings/TemperatureUnits" />
<xsl:variable name="PressUnit"  select="/JOBFile/Environment/DisplaySettings/PressureUnits" />

<!-- Setup conversion factor for coordinate and distance values -->
<!-- Dist/coord values in JobXML file are always in metres -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">3.280839895</xsl:when>
    <xsl:when test="$DistUnit='USSurveyFeet'">3.2808333333357</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for angular values -->
<!-- Angular values in JobXML file are always in decimal degrees -->
<xsl:variable name="AngleConvFactor">
  <xsl:choose>
    <xsl:when test="$AngleUnit='DMSDegrees'">1.0</xsl:when>
    <xsl:when test="$AngleUnit='Gons'">1.111111111111</xsl:when>
    <xsl:when test="$AngleUnit='Mils'">17.77777777777</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">true</xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">true</xsl:when>
    <xsl:otherwise>false</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for pressure values -->
<!-- Pressure values in JobXML file are always in millibars (hPa) -->
<xsl:variable name="PressConvFactor">
  <xsl:choose>
    <xsl:when test="$PressUnit='MilliBar'">1.0</xsl:when>
    <xsl:when test="$PressUnit='InchHg'">0.029529921</xsl:when>
    <xsl:when test="$PressUnit='mmHg'">0.75006</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>


<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >

  <!-- Select Reductions node to process -->
  <xsl:apply-templates select="JOBFile/Reductions" />

</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** Reductions Node Processing ******************* -->
<!-- **************************************************************** -->
<xsl:template match="Reductions">
  <xsl:apply-templates select="Point"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- **************** Grid Point Details Output ********************* -->
<!-- **************************************************************** -->
<xsl:template name="GridPoint">
  <xsl:variable name="PtStr3600">
    <xsl:call-template name="PadRight">
      <xsl:with-param name="StringWidth" select="14"/>
      <xsl:with-param name="TheString">
        <xsl:value-of select="Name" />
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="PtStr3300">
    <xsl:call-template name="PadLeft">
      <xsl:with-param name="StringWidth" select="12"/>
      <xsl:with-param name="TheString">
        <xsl:value-of select="Name" />
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="NthStr">
    <xsl:call-template name="PadLeft">
      <xsl:with-param name="StringWidth" select="15"/>
      <xsl:with-param name="TheString">
        <xsl:variable name="North" select="Grid/North" />
        <xsl:value-of select="format-number($North * $DistConvFactor, $DecPl3, 'Standard')" />
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="EastStr">
    <xsl:call-template name="PadLeft">
      <xsl:with-param name="StringWidth" select="15"/>
      <xsl:with-param name="TheString">
        <xsl:variable name="East" select="Grid/East" />
        <xsl:value-of select="format-number($East * $DistConvFactor, $DecPl3, 'Standard')" />
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="ElevStr">
    <xsl:call-template name="PadLeft">
      <xsl:with-param name="StringWidth" select="15"/>
      <xsl:with-param name="TheString">
        <xsl:variable name="Elev" select="Grid/Elevation" />
        <xsl:value-of select="format-number($Elev * $DistConvFactor, $DecPl3, 'Standard')"/>
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="CodeStr3600">
    <xsl:call-template name="PadRight">
      <xsl:with-param name="StringWidth" select="13"/>
      <xsl:with-param name="TheString">
        <xsl:value-of select="Code" />
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="CodeStr3300">
    <xsl:call-template name="PadLeft">
      <xsl:with-param name="StringWidth" select="5"/>
      <xsl:with-param name="TheString">
        <xsl:value-of select="Code" />
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="MarkingsStr">
    <xsl:choose>
      <xsl:when test="$FormatType='Default 3600 markings'">
        <xsl:value-of select="concat($PtStr3600, $CodeStr3600)"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="concat('          ', $CodeStr3300, $PtStr3300)"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="UnitsStr">
    <xsl:choose>
      <xsl:when test="$DistUnit='Metres'"><xsl:value-of select="' m   '"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="' ft  '"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="NorthingStr">
    <xsl:choose>
      <xsl:when test="contains($NthStr, '?')"><xsl:value-of select="'                    '"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="concat($NthStr, $UnitsStr)"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="EastingStr">
    <xsl:choose>
      <xsl:when test="contains($EastStr, '?')"><xsl:value-of select="'                    '"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="concat($EastStr, $UnitsStr)"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="ElevationStr">
    <xsl:choose>
      <xsl:when test="contains($ElevStr, '?')"><xsl:value-of select="'                    '"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="concat($ElevStr, $UnitsStr)"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="CountStr">
    <xsl:value-of select="format-number(position(), '00000')"/>
  </xsl:variable>

  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">
      <xsl:value-of select="concat('For M5|Adr ', $CountStr, '|PI1 ', $MarkingsStr, '|N_', $NorthingStr, '|E_', $EastingStr, '|Z ', $ElevationStr, '| ')"/>
    </xsl:when>
    <xsl:when test="$CoordOrder='East-North-Elevation'">
      <xsl:value-of select="concat('For M5|Adr ', $CountStr, '|PI1 ', $MarkingsStr, '|E_', $EastingStr, '|N_', $NorthingStr, '|Z ', $ElevationStr, '| ')"/>
    </xsl:when>
    <xsl:when test="$CoordOrder='Y-X-Z'">
      <xsl:value-of select="concat('For M5|Adr ', $CountStr, '|PI1 ', $MarkingsStr, '|Y ', $EastingStr, '|X ', $NorthingStr, '|Z ', $ElevationStr, '| ')"/>
    </xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">
      <xsl:value-of select="concat('For M5|Adr ', $CountStr, '|PI1 ', $MarkingsStr, '|X ', $NorthingStr, '|Y ', $EastingStr, '|Z ', $ElevationStr, '| ')"/>
    </xsl:when>
  </xsl:choose>
  <xsl:call-template name="NewLine"/>

</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Reductions Point Output ********************* -->
<!-- **************************************************************** -->
<xsl:template match="Point">
  <xsl:call-template name="GridPoint"/> 

</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** New Line Output ************************* -->
<!-- **************************************************************** -->
<xsl:template name="NewLine">
<xsl:text>&#10;</xsl:text>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Pad a string to the left with spaces *************** -->
<!-- **************************************************************** -->
<xsl:template name="PadLeft">
  <xsl:param name="StringWidth"/>
  <xsl:param name="TheString"/>
  <xsl:choose>
    <xsl:when test="$StringWidth = '0'">
      <xsl:value-of select="normalize-space($TheString)"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:variable name="PaddedStr" select="concat('                                       ', $TheString)"/>
      <xsl:value-of select="substring($PaddedStr, string-length($PaddedStr) - $StringWidth + 1)"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Pad a string to the right with spaces ************** -->
<!-- **************************************************************** -->
<xsl:template name="PadRight">
  <xsl:param name="StringWidth"/>
  <xsl:param name="TheString"/>
  <xsl:choose>
    <xsl:when test="$StringWidth = '0'">
      <xsl:value-of select="normalize-space($TheString)"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:variable name="PaddedStr" select="concat($TheString, '                                       ')"/>
      <xsl:value-of select="substring($PaddedStr, 1, $StringWidth)"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


</xsl:stylesheet>